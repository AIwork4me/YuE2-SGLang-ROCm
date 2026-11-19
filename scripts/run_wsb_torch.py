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
    """Durable, serialized append; refuse an unquarantined torn tail."""
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.fstat(fd).st_size
        if size:
            os.lseek(fd, -1, os.SEEK_END)
            if os.read(fd, 1) != b"\n":
                raise ValueError("Journal ends in an unquarantined torn record")
        offset = 0
        while offset < len(data):
            n = os.write(fd, data[offset:])
            if n <= 0:
                raise OSError("Journal write returned zero bytes")
            offset += n
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_journal(path: Path) -> tuple[set[str], list[str]]:
    """Read a journal without ever treating torn data as a completion.

    The incomplete final record is copied, fsynced, then truncated with
    fsync under the same file lock as append. A corrupt *complete* record
    fails closed. A later 'failed' event cancels an earlier 'complete'.
    """
    completed: set[str] = set()
    problems: list[str] = []
    if not path.exists():
        return completed, problems
    with path.open("r+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            raw = stream.read()
            if raw and not raw.endswith(b"\n"):
                last_break = raw.rfind(b"\n") + 1
                tail = raw[last_break:]
                sidecar = path.with_name(
                    path.name + ".corrupt-tail-" + uuid.uuid4().hex + ".bin"
                )
                with sidecar.open("xb") as f:
                    f.write(tail)
                    f.flush()
                    os.fsync(f.fileno())
                stream.seek(last_break)
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
                raw = raw[:last_break]
                problems.append(
                    f"torn final line quarantined in {sidecar.name} (not counted)"
                )
            for no, line in enumerate(raw.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ValueError(
                        f"Invalid complete interior journal line {no}; manual audit required"
                    ) from exc
                if not isinstance(rec, dict) or not isinstance(rec.get("id"), str):
                    raise ValueError(f"Invalid journal schema at line {no}")
                if rec.get("status") == "complete":
                    completed.add(rec["id"])
                elif rec.get("status") == "failed":
                    if rec["id"] in completed:
                        problems.append(
                            f"id {rec['id']!r} both complete and failed; latest status wins"
                        )
                    completed.discard(rec["id"])
                else:
                    raise ValueError(f"Invalid journal status at line {no}")
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return completed, problems


def resume_verified_candidate(candidate: Path, candidate_id: str,
                              completed: set[str], verify_result,
                              journal: Path) -> tuple[bool, bool]:
    """Return (skip_generation, was_recovered_or_invalidated).

    A verified artifact is authoritative even if the journal append was
    interrupted. A missing/broken claimed completion MUST be regenerated.
    The caller updates its completed counter on invalidation/recovery.
    """
    claimed = candidate_id in completed
    if candidate.is_symlink():
        raise RuntimeError("Refusing symlink candidate artifact")
    if candidate.exists():
        try:
            receipt = verify_result(candidate)
        except Exception:
            if claimed:
                completed.discard(candidate_id)
                return False, True
            return False, False
        if claimed:
            return True, False
        atomic_append(journal, {
            "id": candidate_id,
            "status": "complete",
            "recovered_from_verified_artifact": True,
            "identity": receipt.get("identity"),
        })
        completed.add(candidate_id)
        return True, True
    if claimed:
        completed.discard(candidate_id)
        return False, True
    return False, False


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


# --------------------------------------------------------------------------
# C2 P3: immutable source snapshots + per-attempt provenance
# (C2.1 P1-A hardening: symlink refusal is TYPE-BASED, not hash-based; writes
#  are crash-safe via tmp+fsync+link so a crash can never leave a partial
#  file at the content-addressed name)
# --------------------------------------------------------------------------
def _publish_snapshot(tmp: Path, final: Path) -> bool:
    """Atomically link tmp -> final (no-clobber). Returns True if THIS call
    created final; False if another writer won the race (their content is
    then verified by the caller)."""
    try:
        os.link(tmp, final)
        return True
    except FileExistsError:
        return False
    finally:
        if os.path.lexists(tmp):
            tmp.unlink()


def _verify_snapshot_file(path: Path, expected_sha: str) -> None:
    """Type-strict verification: the snapshot must be a REGULAR FILE (never a
    symlink — even one whose target content hashes correctly, since the
    symlink itself is mutable state outside the store), and its bytes must
    hash to expected_sha."""
    if path.is_symlink():
        raise RuntimeError(f"worker snapshot is a SYMLINK (refused even if "
                           f"target content matches): {path.name}")
    if not path.is_file():
        raise RuntimeError(f"worker snapshot path has unexpected type: {path.name}")
    actual = sha256_file(path)
    if actual != expected_sha:
        raise RuntimeError(f"worker snapshot tampered: {path.name} "
                           f"hashes {actual[:12]}… not {expected_sha[:12]}…")


def snapshot_worker_source(runs_dir: Path) -> tuple[Path, str]:
    """Write-once worker source snapshot at worker_sources/<sha>.py.

    Rules:
      * content-addressed: the EXECUTED file is always the snapshot whose name
        is its own sha256 — a modified worker is a NEW sha, never an overwrite;
      * an existing snapshot must be a REGULAR FILE (symlink refused on TYPE)
        and hash-verify, else refuse (tamper detection);
      * creation is crash-safe: content lands in a private tmp name (fsynced),
        then a hardlink publishes it atomically — a crash mid-write can never
        leave a partial file at the content-addressed name;
      * the legacy mutable `_gen_worker.py` is never overwritten: if present
        with different content it is preserved untouched (legacy evidence).
    """
    src_dir = runs_dir / "worker_sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    if src_dir.is_symlink():
        raise RuntimeError("worker_sources is a symlink — refusing (escape)")
    worker_sha = hashlib.sha256(GEN_WORKER.encode()).hexdigest()
    snap = src_dir / f"{worker_sha}.py"
    if os.path.lexists(snap):
        _verify_snapshot_file(snap, worker_sha)
    else:
        tmp = src_dir / f".snap-tmp-{uuid.uuid4().hex}"
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
        try:
            os.write(fd, GEN_WORKER.encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        created = _publish_snapshot(tmp, snap)
        # verify whichever instance won the race (ours or the concurrent one)
        _verify_snapshot_file(snap, worker_sha)
        if not created:
            # concurrent writer produced identical content — fine
            pass
    legacy = runs_dir / "_gen_worker.py"
    if legacy.is_symlink():
        raise RuntimeError("legacy _gen_worker.py is a symlink — refusing")
    if legacy.is_file():
        legacy_sha = sha256_file(legacy)
        if legacy_sha != worker_sha:
            preserve = src_dir / f"{legacy_sha}.py"
            if not os.path.lexists(preserve):
                tmp = src_dir / f".snap-tmp-{uuid.uuid4().hex}"
                fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
                try:
                    os.write(fd, legacy.read_bytes())
                    os.fsync(fd)
                finally:
                    os.close(fd)
                _publish_snapshot(tmp, preserve)
    elif not os.path.lexists(legacy):
        # fresh run: also expose the conventional path for older tooling,
        # write-once, same content
        tmp = src_dir / f".snap-tmp-{uuid.uuid4().hex}"
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
        try:
            os.write(fd, GEN_WORKER.encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        _publish_snapshot(tmp, legacy)
    return snap, worker_sha


def write_provenance_receipt(path: Path, obj: dict) -> None:
    """O_EXCL write-once receipt (launched/result). Refuses duplicates."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
    try:
        os.write(fd, (json.dumps(obj, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def start_driver_session(runs_dir: Path, args, worker_sha: str,
                         driver_sha: str) -> str:
    """One provenance session per driver start: environment identity is
    captured once per contiguous execution (a torch-import probe per candidate
    would cost hours across 384 candidates)."""
    session_id = uuid.uuid4().hex
    sessions = runs_dir / "provenance" / "driver_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    write_provenance_receipt(sessions / f"{session_id}.json", {
        "session_id": session_id,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "driver_source_sha256": driver_sha,
        "worker_source_sha256": worker_sha,
        "runtime": detect_runtime(args),
        "driver_pid": os.getpid(),
        "driver_cmdline": "/proc/self/cmdline unavailable; see run log",
    })
    return session_id


def attempt_receipt_path(runs_dir: Path, candidate_id: str, attempt_id: str,
                         phase: str) -> Path:
    d = runs_dir / "provenance" / candidate_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{attempt_id}.{phase}.json"


GEN_WORKER = r'''
import json, os, sys, time, traceback, uuid
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
    if tmp.is_symlink() or out.is_symlink():
        raise RuntimeError("Refusing symlink output paths")
    if tmp.exists():
        # Unique names prevent overwrite when the same candidate is retried.
        import shutil
        q = tmp.with_name(ident + ".partial.quarantine-" + uuid.uuid4().hex)
        shutil.move(str(tmp), str(q))
    tmp.mkdir(parents=True, exist_ok=False)
    if out.exists():
        import shutil
        q = out.with_name(ident + ".quarantine-" + uuid.uuid4().hex)
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
    ap.add_argument("--worker-timeout-s", type=int, default=10800,
                    help="Bound one worker process (default 10800 seconds)")
    args = ap.parse_args()
    if args.worker_timeout_s <= 0:
        ap.error("--worker-timeout-s must be positive")
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
    # VOLATILE fields (timestamps) live OUTSIDE the compared identity — a
    # resume must compare STABLE facts only (defect found on fresh image:
    # created_at_utc inside the identity made every resume a "mismatch").
    ident = {
        "identity_schema": "armA-run-config/v2",
        "driver_protocol": "armA-driver/1",  # compared; bumps ONLY on generation-semantics change
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
        "protocol_lock": "configs/benchmark.lock.yaml profile=benchmark-reproduction frozen 2026-11-11",
        "runtime": detect_runtime(args),
    }
    # Informational (recorded once, never compared): tooling evolves during a
    # multi-day campaign; the per-candidate journal + _gen_worker.py capture
    # what actually executed. driver_protocol above carries semantic identity.
    info = {
        "driver_source_sha256": sha256_file(Path(__file__).resolve()),
        "generator_worker_sha256": hashlib.sha256(GEN_WORKER.encode()).hexdigest(),
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    rc_path = args.runs / "run_config.json"
    # never part of the compared contract (timestamps + informational tooling hashes)
    VOLATILE_KEYS = ("created_at_utc", "driver_source_sha256",
                     "generator_worker_sha256", "informational_note")

    def stable(d: dict) -> dict:
        return {k: v for k, v in d.items() if k not in VOLATILE_KEYS}

    if rc_path.is_file():
        prev = json.loads(rc_path.read_text())
        if stable(prev) != stable(ident):
            print(f"FATAL: run identity mismatch (resume requires identical config)")
            print(f"  existing: {json.dumps(stable(prev))}")
            print(f"  requested: {json.dumps(stable(ident))}")
            return 3
    else:
        rc_path.write_text(json.dumps({**ident, **info}, indent=2) + "\n")

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
    allowed_ids = {
        f"wsb_{row['prompt_index']:03d}_r{j}_s{row['candidate_ar_seeds'][j]}"
        for row in rows for j in (0, 1)
    }
    if not done_ok.issubset(allowed_ids):
        raise ValueError("Journal contains completed ID outside frozen run scope")
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

    # C2 P3: execute the CONTENT-ADDRESSED snapshot; never a mutable path
    worker_path, worker_sha = snapshot_worker_source(args.runs)
    driver_sha = sha256_file(Path(__file__).resolve())
    session_id = start_driver_session(args.runs, args, worker_sha, driver_sha)
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
                cand = args.runs / "songs" / ident_c
                was_complete = ident_c in done_ok
                skip, changed = resume_verified_candidate(
                    cand, ident_c, done_ok, verify_result, journal
                )
                if changed:
                    completed += (1 if not was_complete and skip else
                                  -1 if was_complete and not skip else 0)
                if skip:
                    continue
                if changed and was_complete:
                    print(f"[armA] {ident_c}: invalid completion quarantined on regeneration",
                          flush=True)
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
                attempt_id = uuid.uuid4().hex
                write_provenance_receipt(
                    attempt_receipt_path(args.runs, ident_c, attempt_id,
                                         "launched"),
                    {"attempt_id": attempt_id, "candidate_id": ident_c,
                     "session_id": session_id,
                     "driver_source_sha256": driver_sha,
                     "worker_source_sha256": worker_sha,
                     "seed": seed, "prompt_index": r["prompt_index"],
                     "candidate_index": j,
                     "launched_at_utc": time.strftime(
                         "%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                t0 = time.time()
                try:
                    proc = subprocess.run(
                        [py, str(worker_path), json.dumps(spec)],
                        capture_output=True, text=True, timeout=args.worker_timeout_s)
                    stdout, stderr = proc.stdout or "", proc.stderr or ""
                except subprocess.TimeoutExpired as exc:
                    proc = None
                    stdout = (exc.stdout or b"")
                    stderr = (exc.stderr or b"")
                    if isinstance(stdout, bytes):
                        stdout = stdout.decode(errors="replace")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode(errors="replace")
                    stderr += f"\nWorker exceeded {args.worker_timeout_s}s; partial preserved"
                status, extra = None, {}
                last = [l for l in stdout.splitlines() if l.strip()]
                for line in reversed(last):
                    if line.startswith("RESULT "):
                        extra = json.loads(line[7:]); status = "complete"; break
                if status != "complete" or proc is None or proc.returncode != 0:
                    err = (stderr or stdout or "Worker did not complete")[-1500:]
                    rec = {"id": ident_c, "status": "failed", "seed": seed,
                           "prompt_index": r["prompt_index"], "candidate_index": j,
                           "error": err, "wall_s": round(time.time() - t0, 1),
                           "attempt_id": attempt_id,
                           "worker_source_sha256": worker_sha,
                           "driver_source_sha256": driver_sha,
                           "session_id": session_id}
                    write_provenance_receipt(
                        attempt_receipt_path(args.runs, ident_c, attempt_id,
                                             "result"),
                        {**rec, "result_at_utc": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                    atomic_append(journal, rec)
                    print(f"[armA] FAILED {ident_c}: {err[:200]}", flush=True)
                    continue
                extra.update({"attempt_id": attempt_id,
                              "worker_source_sha256": worker_sha,
                              "driver_source_sha256": driver_sha,
                              "session_id": session_id})
                write_provenance_receipt(
                    attempt_receipt_path(args.runs, ident_c, attempt_id,
                                         "result"),
                    {"attempt_id": attempt_id, "candidate_id": ident_c,
                     "status": "complete", "seed": seed,
                     "prompt_index": r["prompt_index"], "candidate_index": j,
                     "audio_seconds": extra.get("audio_seconds"),
                     "identity": extra.get("identity"),
                     "worker_source_sha256": worker_sha,
                     "driver_source_sha256": driver_sha,
                     "session_id": session_id,
                     "wall_s": extra.get("wall_s"),
                     "result_at_utc": time.strftime(
                         "%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                atomic_append(journal, extra)
                completed += 1
                eta_h = (time.time() - t_start) / max(1, completed - (len(done_ok))) * (total - completed) / 3600
                print(f"[armA] complete {ident_c} wall={extra.get('wall_s')}s "
                      f"({completed}/{total}, eta~{eta_h:.1f}h)", flush=True)
    print(f"[armA] finished pass: {completed}/{total} complete", flush=True)
    return 0 if completed == total else 6


if __name__ == "__main__":
    raise SystemExit(main())
