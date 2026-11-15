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
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
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
    """Crash-consistent journal append (RCA-F2).

    fsync before close so a completed candidate can never be lost to a crash
    after the process reported it; the append itself is a single small write to
    an O_APPEND fd, so a crash mid-write can only ever tear the FINAL line,
    which read_journal() tolerates (and reports) explicitly.
    """
    data = (json.dumps(obj) + "\n").encode()
    with open(path, "ab") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def read_journal(path: Path) -> tuple[set[str], list[str]]:
    """Read a completion journal crash-consistently (RCA-F2).

    Returns (complete_ids, problems).
      * a torn/partial FINAL line (crash during append) is reported as a
        problem but NOT treated as completion — the campaign regenerates it;
      * an unparseable INTERIOR line is reported (should be impossible with
        single-write O_APPEND appends; would indicate external tampering);
      * duplicate completion records are deduplicated; a record marked
        complete and later failed for the same id is a conflict → problem
        (the resume verify_result gate is the real authority either way).
    A campaign must never falsely count a candidate as complete.
    """
    complete: set[str] = set()
    problems: list[str] = []
    if not path.is_file():
        return complete, problems
    lines = path.read_text().splitlines()
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            kind = ("torn final line (crash during append) — not counted complete"
                    if idx == len(lines) - 1 else
                    "unparseable interior line — possible tampering")
            problems.append(f"{path.name}:{idx + 1}: {kind}: {line[:120]!r}")
            continue
        status = rec.get("status")
        if status == "complete":
            complete.add(rec["id"])
        elif status == "failed" and rec.get("id") in complete:
            problems.append(f"{path.name}:{idx + 1}: id {rec.get('id')!r} both "
                            f"complete and failed — deferring to artifact verify")
    return complete, problems


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


def detect_runtime(args) -> dict:
    """Best-effort capture of the GENERATION interpreter's torch/HIP/GPU stack.

    Probed by running a tiny snippet in the child python (the actual
    generation interpreter), so the identity records what will really execute.
    Failures degrade to explicit 'unknown' markers — never silent guesses.
    """
    probe = (
        "import json,sys\n"
        "out={'python':sys.version.split()[0]}\n"
        "try:\n"
        "    import torch\n"
        "    out['torch']=torch.__version__\n"
        "    out['hip']=getattr(torch.version,'hip',None)\n"
        "    if torch.cuda.is_available():\n"
        "        p=torch.cuda.get_device_properties(0)\n"
        "        out['gpu']=p.name; out['gcn_arch']=getattr(p,'gcnArchName','')\n"
        "        out['vram_bytes']=p.total_memory\n"
        "except Exception as e:\n"
        "    out['torch_error']=f'{type(e).__name__}: {e}'\n"
        "print(json.dumps(out))\n"
    )
    try:
        r = subprocess.run([child_python(args), "-c", probe],
                           capture_output=True, text=True, timeout=180)
        for line in reversed((r.stdout or "").splitlines()):
            if line.startswith("{"):
                return json.loads(line)
    except Exception:
        pass
    return {"python": "unknown", "torch": "unknown", "hip": "unknown"}


GEN_WORKER = r'''
import json, os, sys, time, traceback
from pathlib import Path

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
    if tmp.exists():
        # RCA-F1: QUARANTINE, never delete — a partial dir is campaign evidence
        # (docs promise quarantine-not-delete; the old rmtree violated that).
        import time as _t, shutil
        q = tmp.with_name(ident + ".partial.quarantine-" + str(int(_t.time())))
        shutil.move(str(tmp), str(q))
    tmp.mkdir(parents=True, exist_ok=True)
    if out.exists():  # quarantine, never delete (immutable artifacts rule)
        import time as _t, shutil
        q = out.with_name(ident + ".quarantine-" + str(int(_t.time())))
        shutil.move(str(out), str(q))
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
    args = ap.parse_args()
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
    run_id = args.run_id or time.strftime("armA%Y%m%dT%H%M%SZ", time.gmtime())
    # RCA-F3: exact experiment identity — enough to prove WHAT ran, not just a
    # short run-id. Everything material to reproduction is recorded; the
    # write-once contract (below) then pins it for the whole campaign.
    ident = {
        "identity_schema": "armA-run-config/v2",
        "run_id": run_id,
        "platform": "gfx1100",
        "arm": "A-torch",
        "backend": args.backend,
        "model_revision": OFFICIAL["model_revision"],
        "vae_revision": OFFICIAL["vae_revision"],
        "model_sha256": OFFICIAL["model_sha256"],
        "vae_sha256": OFFICIAL["vae_sha256"],
        "manifest_sha256": OFFICIAL["manifest_sha256"],
        "evaluator_bundle_sha256": "bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd",
        "generation_contract": {
            "cot": OFFICIAL["cot"], "cfg_scale": OFFICIAL["cfg_scale"],
            "candidates_per_prompt": OFFICIAL["candidates"],
            "seeds": "831001+i / 831019+i via frozen manifest candidate_ar_seeds",
            "memory_budget_gib": OFFICIAL["memory_budget_gib"],
            "request_contract": "SongRequest.text() == row.generation_prompt (asserted per candidate)",
        },
        "driver_source_sha256": sha256_file(Path(__file__).resolve()),
        "generator_worker_sha256": hashlib.sha256(GEN_WORKER.encode()).hexdigest(),
        "protocol_lock": "configs/benchmark.lock.yaml profile=benchmark-reproduction frozen 2026-11-11",
        "runtime": detect_runtime(args),
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
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
    done_ok, journal_problems = read_journal(journal)
    for p in journal_problems:
        print(f"[journal] WARNING: {p}", flush=True)

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

    from gpu_lock import gpu_ownership  # RCA-F4: single-GPU ownership policy
    with gpu_ownership(f"armA-campaign:{run_id}", wait_s=float(
            os.environ.get("YUE2_GPU_LOCK_WAIT_S", "3600"))):
        for r in rows:
            for j, seed in enumerate(r["candidate_ar_seeds"][:2]):
                ident_c = f"wsb_{r['prompt_index']:03d}_r{j}_s{seed}"
                if ident_c in done_ok:
                    cand = args.runs / "songs" / ident_c
                    try:
                        verify_result(cand)
                        continue  # verified complete: skip
                    except Exception:
                        print(f"[armA] {ident_c}: journal said complete but verify failed -> regenerating", flush=True)
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
                proc = subprocess.run([py, str(worker_path), json.dumps(spec)],
                                      capture_output=True, text=True)
                status, extra = None, {}
                last = [l for l in (proc.stdout or "").splitlines() if l.strip()]
                for line in reversed(last):
                    if line.startswith("RESULT "):
                        extra = json.loads(line[7:]); status = "complete"; break
                if status != "complete":
                    err = (proc.stderr or proc.stdout or "")[-1500:]
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
