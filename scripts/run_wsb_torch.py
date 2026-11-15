#!/usr/bin/env python3
"""run_wsb_torch.py — resumable driver for the OFFICIAL native-PyTorch WSB arm.

Implements the official `code/generate.py` (WildSongBench @ e361b85a)
generation semantics exactly — same seeds, same request contract
(`SongRequest.text() == row['generation_prompt']` asserted), same artifact
layout via `song.save_artifacts()` + official `verify_result` — with the
campaign durability the official script lacks:

  * write-once run identity (refuses config mixing on resume)
  * write-once evaluation_inputs.jsonl
  * per-candidate journal (atomic appends) with resume-skip for verified
    candidates only (official verify_result re-run on resume)
  * graceful SIGINT/SIGTERM (finish in-flight candidate, then stop)
  * quarantine (never delete) partially written candidate dirs
  * disk-safety thresholds (default: stop < 100 GiB free)

Backend: `torch-eager` by default (DEV-1: the graph path's varlen
FlashAttention capability probe is schema-only and the ROCm kernel rejects
seqused_k; torch-eager is the official public-SDPA backend). `--backend
torch` is selectable for CUDA hosts.

Usage:
  YUE2_WORKSPACE=<ws> python scripts/run_wsb_torch.py --runs <dir> \
      [--venv-python <path>] [--backend torch-eager] [--indices 0 1 ...]
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from yue2_workspace import resolve_workspace

WS = None  # resolved in main() (strict)

OFFICIAL = {
    "candidates": 2, "cot": "full", "cfg_scale": 1.0,
    "memory_budget_gib": 24, "backend": "torch-eager",
    "model_revision": "1a96eca688d6ae5d7f0feb88573fec89920fcd19",
    "vae": "m-a-p/YuE2-Vae-legacy",
    "vae_revision": "b54118f0fc462f08999d1ec07e88817f4ee3f770",
    "model_sha256": "1d55c42c1a9875c34f5d736e15078449992b044e807ce2a138e6cf289a1e59e9",
    "vae_sha256": "b6d283628913bb41145ba99e2314eef613905ee95f690eb70e8212d5f4965044",
    "manifest_sha256": "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0",
}
MIN_FREE_GB = float(os.environ.get("YUE2_MIN_FREE_GB", "100"))


def atomic_append(path: Path, obj: dict) -> None:
    """Append a durable JSONL record under an advisory lock.

    A single write is not sufficient to promise crash atomicity for regular
    files. A torn final record is quarantined on restart by read_journal().
    Never replace the journal or report a partial record as complete.
    """
    data = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if os.fstat(fd).st_size:
            with path.open("rb") as reader:
                reader.seek(-1, os.SEEK_END)
                if reader.read(1) != b"\n":
                    raise ValueError("Journal has an incomplete final record; recover before append")
        written = 0
        while written < len(data):
            n = os.write(fd, data[written:])
            if n <= 0:
                raise OSError("short journal write")
            written += n
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_journal(path: Path) -> list[dict]:
    """Keep a torn final record in a private sidecar, then read complete rows.

    Corruption in a newline-terminated record is NOT auto-repaired, because
    that could conceal an invalid or forged historical completion.
    """
    if not path.exists():
        return []
    raw = path.read_bytes()
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        end = raw.rfind(b"\n") + 1
        tail = raw[end:]
        backup = path.with_name(path.name + ".corrupt-tail-" + uuid.uuid4().hex + ".bin")
        with backup.open("xb") as out:
            out.write(tail)
            out.flush()
            os.fsync(out.fileno())
        with path.open("r+b") as stream:
            stream.truncate(end)
            stream.flush()
            os.fsync(stream.fileno())
        raw = raw[:end]
        print(f"[armA] quarantined incomplete journal tail in {backup.name}", flush=True)
    records = []
    for line_no, raw_line in enumerate(raw.splitlines(), 1):
        try:
            record = json.loads(raw_line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid complete journal record on line {line_no}") from exc
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError(f"Invalid journal schema on line {line_no}")
        records.append(record)
    return records


def quarantine_existing(path: Path) -> Path | None:
    """Rename, never delete, an incomplete or invalid candidate bundle."""
    if path.is_symlink():
        raise RuntimeError(f"Refusing to quarantine symlink: {path}")
    if not path.exists():
        return None
    destination = path.with_name(path.name + ".quarantine-" + uuid.uuid4().hex)
    path.rename(destination)
    return destination


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def disk_free_gb(path: Path) -> float:
    import shutil
    return shutil.disk_usage(str(path)).free / 2**30


def child_python(args) -> str:
    if args.venv_python:
        return args.venv_python
    return sys.executable


GEN_WORKER = r'''
import json, os, sys, time, traceback, uuid
from pathlib import Path

def quarantine_existing(path):
    if path.is_symlink():
        raise RuntimeError(f"Refusing to quarantine symlink: {path}")
    if path.exists():
        q = path.with_name(path.name + ".quarantine-" + uuid.uuid4().hex)
        path.rename(q)
        return q
    return None

def main() -> int:
    spec = json.loads(sys.argv[1])
    sys.path.insert(0, spec["ws"] + "/benchmark/WildSongBench/evaluation/wsb_metrics")
    import torch
    from yue2 import YuE2Pipeline
    from yue2.protocol import SongRequest
    from yue2.storage import verify_result
    row = spec["row"]
    seed = spec["seed"]; j = spec["candidate_index"]
    ident = f"wsb_{row['prompt_index']:03d}_r{j}_s{seed}"
    out = Path(spec["out"]) / "songs" / ident
    tmp = out.with_name(ident + ".partial")
    quarantine_existing(tmp)
    tmp.mkdir(parents=True, exist_ok=False)
    quarantine_existing(out)
    t0 = time.time()
    with YuE2Pipeline.from_pretrained(
            "m-a-p/YuE2-3B", revision=spec["model_revision"], vae=spec["vae"],
            vae_revision=spec["vae_revision"], cache_dir=spec.get("cache_dir"),
            backend=spec["backend"], device="cuda:0",
            memory_budget_gib=spec["memory_budget_gib"]) as pipe:
        assert sha256_file(pipe.model_dir / "model.safetensors") == spec["model_sha256"]
        assert sha256_file(pipe.vae_dir / "model.safetensors") == spec["vae_sha256"]
        request = dict(id=ident, style=row["style"], lyrics=row["lyrics"],
                       cot="full", cfg_scale=1.0, seed=seed)
        assert SongRequest(**request).text() == row["generation_prompt"], \
            "request contract violated vs frozen manifest"
        song = pipe(**request)
        song.save_artifacts(tmp)
        receipt = verify_result(tmp)
    os.replace(tmp, out)  # atomic promotion of the completed bundle
    result = {"id": ident, "status": "complete",
              "prompt_index": row["prompt_index"], "candidate_index": j, "seed": seed,
              "identity": receipt["identity"], "truncated": receipt["truncated"],
              "audio_seconds": receipt["audio_seconds"],
              "wall_s": round(time.time() - t0, 1)}
    print("RESULT " + json.dumps(result), flush=True)
    return 0

def sha256_file(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"id": "?", "status": "failed",
                          "error": f"{type(exc).__name__}: {exc}",
                          "traceback": traceback.format_exc()[-2000:]}), flush=True)
        raise SystemExit(1)
'''


def main() -> int:
    global WS
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--backend", default=OFFICIAL["backend"],
                    choices=("torch", "torch-eager", "vllm"))
    ap.add_argument("--indices", type=int, nargs="*", default=None,
                    help="prompt indices (default: all 192)")
    ap.add_argument("--venv-python", default=None,
                    help="python of the generation venv (default: this interpreter)")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--worker-timeout-seconds", type=int, default=3600,
                    help="per-candidate worker timeout (default 3600; must be >0)")
    args = ap.parse_args()
    if args.worker_timeout_seconds <= 0:
        ap.error("--worker-timeout-seconds must be positive")
    if WS is None:
        WS = resolve_workspace(__file__)

    manifest_path = WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
    if sha256_file(manifest_path) != OFFICIAL["manifest_sha256"]:
        print("FATAL: reproduction_manifest.jsonl does not match the frozen pin")
        return 2
    rows = [json.loads(l) for l in manifest_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 192 and [r["prompt_index"] for r in rows] == list(range(192))
    if args.indices is not None:
        wanted = set(args.indices)
        rows = [r for r in rows if r["prompt_index"] in wanted]

    args.runs.mkdir(parents=True, exist_ok=True)
    # Linux advisory lease prevents two drivers corrupting the same run.
    lock_fd = os.open(args.runs / ".driver.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        print("FATAL: another Arm A driver owns this run directory", flush=True)
        return 7
    # The process retains lock_fd until exit, including while workers run.
    run_id = args.run_id or time.strftime("armA%Y%m%dT%H%M%SZ", time.gmtime())
    ident = {"run_id": run_id, "platform": "gfx1100", "arm": "A-torch",
             "backend": args.backend,
             "model_revision": OFFICIAL["model_revision"],
             "vae_revision": OFFICIAL["vae_revision"],
             "manifest_sha256": OFFICIAL["manifest_sha256"]}
    rc_path = args.runs / "run_config.json"
    if rc_path.is_file():
        prev = json.loads(rc_path.read_text())
        if prev != ident:
            print(f"FATAL: run identity mismatch (resume requires identical config)")
            print(f"  existing: {json.dumps(prev)}")
            print(f"  requested: {json.dumps(ident)}")
            return 3
    else:
        rc_path.write_text(json.dumps(ident, indent=2) + "\n")

    # write-once evaluation inputs
    inputs = args.runs / "evaluation_inputs.jsonl"
    expected_lines = "".join(
        json.dumps({"prompt_index": r["prompt_index"], "candidate_index": j,
                    "seed": r["candidate_ar_seeds"][j],
                    "path": f"songs/wsb_{r['prompt_index']:03d}_r{j}_s{r['candidate_ar_seeds'][j]}"})
        + "\n"
        for r in rows for j in (0, 1))
    if inputs.is_file():
        if inputs.read_text() != expected_lines:
            print("FATAL: evaluation_inputs.jsonl differs from write-once expectation")
            return 3
    else:
        inputs.write_text(expected_lines)

    journal = args.runs / "generation_manifest.jsonl"
    expected_ids = {
        f"wsb_{row['prompt_index']:03d}_r{j}_s{row['candidate_ar_seeds'][j]}"
        for row in rows for j in (0, 1)
    }
    state: dict[str, str] = {}
    for entry in read_journal(journal):
        if entry["id"] not in expected_ids:
            raise ValueError("Journal contains a candidate outside the frozen run input")
        if entry.get("status") not in {"complete", "failed"}:
            raise ValueError("Journal contains an invalid candidate status")
        state[entry["id"]] = entry["status"]  # last event wins
    done_ok = {ident for ident, status in state.items() if status == "complete"}

    # Add a source receipt WITHOUT changing legacy run_config.json shape.
    # Old runs lack provenance for their earlier driver version; report honestly.
    source_receipt = args.runs / "harness_source_receipt.json"
    current_source = {
        "schema": 1,
        "driver_sha256": sha256_file(Path(__file__).resolve()),
        "worker_sha256": hashlib.sha256(GEN_WORKER.encode("utf-8")).hexdigest(),
        "python": sys.executable,
    }
    if source_receipt.is_file():
        earlier = json.loads(source_receipt.read_text(encoding="utf-8"))
        if any(earlier.get(k) != v for k, v in current_source.items()):
            raise RuntimeError(
                "Harness source/runtime differs from the write-once receipt; "
                "start a separate run or explicitly reconcile the provenance."
            )
    else:
        current_source["historical_rows_without_source_receipt"] = len(read_journal(journal))
        # An existing campaign may have a partial old driver history; do not
        # retroactively attribute those records to this newly recorded driver.
        with source_receipt.open("x", encoding="utf-8") as output:
            json.dump(current_source, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())

    sys.path.insert(0, str(WS / "benchmark/WildSongBench/evaluation/wsb_metrics"))
    from yue2.storage import verify_result  # reuse for resume verification

    stop = {"requested": False}
    def _sig(signum, frame):
        if not stop["requested"]:
            print(f"[signal {signum}] graceful stop requested; finishing in-flight candidate, then exiting", flush=True)
        stop["requested"] = True
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    worker_path = args.runs / "_gen_worker.py"
    worker_path.write_text(GEN_WORKER)
    py = child_python(args)
    completed = len(done_ok)
    total = len(rows) * 2
    print(f"[armA] run={run_id} backend={args.backend} total={total} already_complete={completed}", flush=True)
    t_start = time.time()
    for r in rows:
        for j, seed in enumerate(r["candidate_ar_seeds"][:2]):
            ident_c = f"wsb_{r['prompt_index']:03d}_r{j}_s{seed}"
            cand = args.runs / "songs" / ident_c
            if ident_c in done_ok:
                try:
                    verify_result(cand)
                    continue  # verified complete: skip
                except Exception:
                    done_ok.discard(ident_c)
                    completed -= 1
                    print(f"[armA] {ident_c}: journal complete, but artifact invalid; quarantine and regenerate", flush=True)
            elif cand.exists() or cand.is_symlink():
                try:
                    receipt = verify_result(cand)
                except Exception:
                    print(f"[armA] {ident_c}: unjournaled invalid artifact; quarantine and regenerate", flush=True)
                else:
                    # Crash after atomic artifact promotion but before the
                    # journal append: preserve and recover the verified output.
                    recovery = {"id": ident_c, "status": "complete",
                                "prompt_index": r["prompt_index"],
                                "candidate_index": j, "seed": seed,
                                "identity": receipt["identity"],
                                "truncated": receipt["truncated"],
                                "audio_seconds": receipt["audio_seconds"],
                                "recovered_from_verified_artifact": True}
                    atomic_append(journal, recovery)
                    done_ok.add(ident_c)
                    completed += 1
                    print(f"[armA] recovered verified unjournaled artifact: {ident_c}", flush=True)
                    continue
            if stop["requested"]:
                print("[armA] stopped by signal; state is resume-safe", flush=True)
                return 4
            if disk_free_gb(args.runs) < MIN_FREE_GB:
                print(f"FATAL: free disk below {MIN_FREE_GB} GiB; stopping safely", flush=True)
                return 5
            spec = {"ws": str(WS), "row": r, "seed": seed, "candidate_index": j,
                    "out": str(args.runs), "backend": args.backend,
                    "model_revision": OFFICIAL["model_revision"], "vae": OFFICIAL["vae"],
                    "vae_revision": OFFICIAL["vae_revision"],
                    "model_sha256": OFFICIAL["model_sha256"],
                    "vae_sha256": OFFICIAL["vae_sha256"],
                    "memory_budget_gib": OFFICIAL["memory_budget_gib"],
                    "cache_dir": args.cache_dir}
            print(f"[armA] generating {ident_c} ({completed+1}/{total})", flush=True)
            t0 = time.time()
            try:
                proc = subprocess.run(
                    [py, str(worker_path), json.dumps(spec)],
                    capture_output=True, text=True, timeout=args.worker_timeout_seconds)
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                proc = None
                stderr += f"\nWorker exceeded {args.worker_timeout_seconds}s; artifacts retained as .partial"
            status, extra = None, {}
            last = [l for l in stdout.splitlines() if l.strip()]
            for line in reversed(last):
                if line.startswith("RESULT "):
                    extra = json.loads(line[7:]); status = "complete"; break
            if status != "complete" or proc is None or proc.returncode != 0:
                err = (stderr or stdout or "Worker exited unsuccessfully")[-1500:]
                rec = {"id": ident_c, "status": "failed", "seed": seed,
                       "prompt_index": r["prompt_index"], "candidate_index": j,
                       "error": err, "wall_s": round(time.time() - t0, 1)}
                atomic_append(journal, rec)
                print(f"[armA] FAILED {ident_c}: {err[:200]}", flush=True)
                continue
            atomic_append(journal, extra)
            completed += 1
            eta_h = (time.time() - t_start) / max(1, completed - (len(done_ok))) * (total - completed) / 3600
            print(f"[armA] complete {ident_c} wall={extra.get('wall_s')}s "
                  f"({completed}/{total}, eta~{eta_h:.1f}h)", flush=True)
    print(f"[armA] finished pass: {completed}/{total} complete", flush=True)
    return 0 if completed == total else 6


if __name__ == "__main__":
    raise SystemExit(main())
