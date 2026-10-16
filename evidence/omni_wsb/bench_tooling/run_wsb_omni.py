#!/usr/bin/env python3
"""run_wsb_omni.py - arm-B WSB generation driver (SGLang-Omni endpoint).

Same hardening as evidence-repo run_wsb.py v2 (immutable run identity,
write-once evaluation_inputs.jsonl, atomic manifest appends, quarantine,
disk-space guard, VRAM/GTT poller, graceful signals, resume).

Arm-B differences (documented in the protocol freeze):
  - server: real sgl-omni serve (bench tree bench/omni-wsb @ c4841f0c =
    PR#1 head 50c91c08 + comment-only 91dccda1 + bench-only artifacts export)
  - endpoint: POST /v1/audio/speech with the nested YuE2 input JSON
    (official dataset style/lyrics verbatim; frozen settings; frozen seeds)
  - WAV body + x-finish-reason header recorded per candidate; artifacts
    bundle written server-side via artifacts_dir, then finalized locally by
    finalize_candidate_omni.py and verified with the frozen official checker.

Official budgets are fixed constants - never reduced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BENCH = Path(__file__).resolve().parent
WS = Path(os.environ.get("YUE2_WORKSPACE", "/workspace/yue2-sglang-rocm-w7900"))
MANIFEST = WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
MODEL_DIR = WS / "models/YuE2-3B"
VAE_DIR = WS / "models/YuE2-Vae-legacy"
FINALIZE = BENCH / "finalize_candidate_omni.py"

OMNI_REPO = Path("/workspace/yue2-omni-pr/repo")
OMNI_COMMIT = os.environ.get("OMNI_COMMIT", "c4841f0c667f76f2cbe83f8268b1b9bf5d6feab5")
PR1_HEAD = "50c91c0888312ae784d3c42d9536665aa517dd9d"
AUTHOR_BASE = "85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9"

OFFICIAL = {
    "cot": "full", "abc": None, "cfg_scale": 1.0,
    "ode_steps": 32, "semantic_max_tokens": 9000, "abc_max_tokens": 4096,
    "vae_core_frames": 1024, "vae_halo_frames": 16,
}
MIN_FREE_GB = float(os.environ.get("YUE2_MIN_FREE_GB", "20"))
STOP = threading.Event()


def atomic_write(path: Path, text: str):
    tmp = tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False,
                                      prefix=path.name + ".", suffix=".tmp")
    tmp.write(text)
    tmp.flush()
    os.fsync(tmp.fileno())
    tmp.close()
    os.replace(tmp.name, path)


def append(path: Path, record: dict):
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


class MemoryPoller:
    def __init__(self, interval=5.0):
        self.interval = interval
        self.samples = 0
        self.peak_gtt_bytes = 0
        self.peak_vram_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _read_sysfs(self) -> tuple[int, int]:
        vram = gtt = 0
        for card in Path("/sys/class/drm").glob("card*"):
            try:
                v = card / "device/mem_info_vis_vram_used"
                g = card / "device/mem_info_gtt_used"
                if v.is_file():
                    vram = max(vram, int(v.read_text()))
                if g.is_file():
                    gtt = max(gtt, int(g.read_text()))
            except (OSError, ValueError):
                continue
        return vram, gtt

    def _run(self):
        while not self._stop.is_set():
            vram, gtt = self._read_sysfs()
            self.peak_vram_bytes = max(self.peak_vram_bytes, vram)
            self.peak_gtt_bytes = max(self.peak_gtt_bytes, gtt)
            self.samples += 1
            self._stop.wait(self.interval)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=15)
        return {"peak_vram_bytes": self.peak_vram_bytes,
                "peak_gtt_bytes": self.peak_gtt_bytes,
                "samples": self.samples}


def post_speech(server: str, payload: dict, timeout: int):
    """POST /v1/audio/speech; return (wav_bytes, headers)."""
    req = urllib.request.Request(
        f"{server}/v1/audio/speech",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), {k.lower(): v for k, v in resp.headers.items()}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def candidate_complete(cand: Path) -> bool:
    try:
        sys.path.insert(0, str(WS / "benchmark" / "wsb_metrics"))
        from artifact_storage import verify_result
        verify_result(cand)
        return True
    except Exception:
        return False


def omni_tree_clean() -> bool:
    out = subprocess.run(["git", "-C", str(OMNI_REPO), "status", "--porcelain"],
                         capture_output=True, text=True, timeout=30)
    head = subprocess.run(["git", "-C", str(OMNI_REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True, timeout=30).stdout.strip()
    return out.returncode == 0 and not out.stdout.strip() and head == OMNI_COMMIT


def check_or_write_run_config(runs_dir: Path, ident: dict) -> int:
    run_config_path = runs_dir / "run_config.json"
    if run_config_path.is_file():
        prev = json.loads(run_config_path.read_text())
        if prev != ident:
            print("FATAL: run_config.json exists with different identity; refusing "
                  "to mix runs. Use a fresh --runs directory.")
            return 3
    else:
        atomic_write(run_config_path, json.dumps(ident, indent=2) + "\n")
    return 0


def check_or_write_inputs(runs_dir: Path, want: str) -> int:
    inputs_path = runs_dir / "evaluation_inputs.jsonl"
    if inputs_path.is_file():
        if inputs_path.read_text() != want:
            print("FATAL: evaluation_inputs.jsonl differs from the selected set; "
                  "refusing to rewrite (no silent protocol changes).")
            return 3
    else:
        atomic_write(inputs_path, want)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--indices", type=int, nargs="*", default=None)
    ap.add_argument("--server", default=os.environ.get("SERVER", "http://127.0.0.1:32100"))
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    if not omni_tree_clean():
        print(f"FATAL: omni tree at {OMNI_REPO} is dirty or not at {OMNI_COMMIT}; "
              "refusing to generate under a moving implementation.")
        return 4

    args.runs = args.runs.resolve()
    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    assert len(rows) == 192 and [r["prompt_index"] for r in rows] == list(range(192)), \
        "frozen manifest shape violated"
    selected = rows if args.indices is None else [r for r in rows
                                                  if r["prompt_index"] in args.indices]
    assert selected, "no manifest rows selected"

    songs = args.runs / "songs"
    songs.mkdir(parents=True, exist_ok=True)
    manifest_path = args.runs / "generation_manifest.jsonl"

    run_id = args.run_id or time.strftime("omni%Y%m%dT%H%M%SZ", time.gmtime())
    ident = {
        "run_id": run_id,
        "platform": "gfx1100", "gpu": "AMD Radeon W7900",
        "serving_stack": "sglang-omni",
        "omni_commit": OMNI_COMMIT,
        "omni_branch": "bench/omni-wsb",
        "pr1_head": PR1_HEAD,
        "author_base": AUTHOR_BASE,
        "instrumentation": "bench-only artifacts_dir export (c4841f0c); audio path "
                           "identical; never pushed upstream",
        "dataset_revision": "m-a-p/WildSongBench@e361b85a8d7365d3079fa9647641a87ce3c8c5b5",
        "model_revision": "m-a-p/YuE2-3B@1a96eca688d6ae5d7f0feb88573fec89920fcd19",
        "vae_revision": "m-a-p/YuE2-Vae-legacy@b54118f0fc462f08999d1ec07e88817f4ee3f770",
        "config": OFFICIAL,
        "candidates": 2,
        "indices": None if args.indices is None else sorted(args.indices),
    }
    rc = check_or_write_run_config(args.runs, ident)
    if rc:
        return rc

    inputs = []
    for row in selected:
        for j, seed in enumerate(row["candidate_ar_seeds"][:2]):
            i = row["prompt_index"]
            ident_str = f"wsb_{i:03d}_r{j}_s{seed}"
            inputs.append({"prompt_index": i, "candidate_index": j,
                           "seed": seed, "path": f"songs/{ident_str}"})
    want = "".join(json.dumps(r) + "\n" for r in inputs)
    rc = check_or_write_inputs(args.runs, want)
    if rc:
        return rc

    def handle(signum, frame):
        STOP.set()
        print(f"\n[signal {signum}] graceful stop requested; finishing in-flight "
              f"candidate, then exiting", flush=True)
    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    poller = MemoryPoller().start()
    started = time.time()
    done = fail = skipped = 0
    quarantine = args.runs / "quarantine"
    try:
        for row in selected:
            if STOP.is_set():
                break
            for j, seed in enumerate(row["candidate_ar_seeds"][:2]):
                if STOP.is_set():
                    break
                i = row["prompt_index"]
                ident_str = f"wsb_{i:03d}_r{j}_s{seed}"
                cand = songs / ident_str
                record = {"id": ident_str, "prompt_index": i, "candidate_index": j,
                          "seed": seed, "source": "m-a-p/WildSongBench@e361b85a",
                          "run_id": run_id, "config": OFFICIAL}

                if candidate_complete(cand):
                    record["status"] = "complete(resumed)"
                    append(manifest_path, record)
                    done += 1
                    skipped += 1
                    print(f"[skip] {ident_str} already complete", flush=True)
                    continue

                if cand.exists():
                    qdir = quarantine / time.strftime("%Y%m%dT%H%M%S")
                    qdir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(cand), str(qdir / ident_str))
                    record["quarantined_from"] = str(qdir / ident_str)
                    append(manifest_path, {**record, "status": "quarantined(partial)"})

                free_gb = shutil.disk_usage(args.runs).free / 2**30
                if free_gb < MIN_FREE_GB:
                    record["status"] = "skipped(disk)"
                    record["free_gb"] = round(free_gb, 1)
                    append(manifest_path, record)
                    fail += 1
                    print(f"[disk] only {free_gb:.1f} GiB free (< {MIN_FREE_GB}); "
                          f"stopping to protect artifacts", flush=True)
                    break

                nested = {
                    "style": row["style"], "lyrics": row["lyrics"],
                    "cot": "full", "seed": seed, "cfg_scale": 1.0,
                    "abc_max_tokens": 4096, "semantic_max_tokens": 9000,
                    "ode_steps": 32, "vae_core_frames": 1024,
                    "vae_halo_frames": 16,
                    "artifacts_dir": str(cand),
                }
                payload = {
                    "model": str(MODEL_DIR),
                    "input": json.dumps(nested, ensure_ascii=False),
                    "voice": "default",
                    "response_format": "wav",
                }
                wav_name = f"{ident_str}.wav"
                t0 = time.time()
                ok, err, retries = False, "", 0
                wav_bytes, headers = None, {}
                for attempt in range(args.max_retries + 1):
                    if STOP.is_set():
                        break
                    try:
                        wav_bytes, headers = post_speech(args.server, payload, args.timeout)
                        ok = (headers.get("content-type", "").startswith("audio/")
                              and wav_bytes[:4] == b"RIFF"
                              and headers.get("x-finish-reason") is not None)
                        if not ok:
                            err = (f"unexpected response: content-type="
                                   f"{headers.get('content-type')} bytes={len(wav_bytes)} "
                                   f"head={wav_bytes[:8]!r}")
                        break
                    except (urllib.error.URLError, TimeoutError, OSError) as exc:
                        err = f"{type(exc).__name__}: {exc}"
                        retries += 1
                        print(f"[retry {attempt}] {ident_str}: {err}", flush=True)
                        time.sleep(10)
                record["wall_s"] = round(time.time() - t0, 2)
                record["retries"] = retries
                if ok and wav_bytes:
                    record["http"] = {
                        "finish_reason": headers.get("x-finish-reason"),
                        "request_id": headers.get("x-request-id"),
                        "content_type": headers.get("content-type"),
                        "wav_sha256": sha256_bytes(wav_bytes),
                        "wav_bytes": len(wav_bytes),
                    }
                    wav = songs / wav_name
                    tmp = wav.with_suffix(".wav.tmp")
                    tmp.write_bytes(wav_bytes)
                    os.replace(tmp, wav)
                    record["status"] = "generated"
                    fin = subprocess.run(
                        [sys.executable, str(FINALIZE),
                         str(cand), str(wav), str(MODEL_DIR), str(VAE_DIR)],
                        capture_output=True, text=True)
                    if fin.returncode == 0 and candidate_complete(cand):
                        detail = json.loads(fin.stdout)
                        record.update(status="complete",
                                      audio_seconds=detail["audio_seconds"],
                                      truncated=detail["truncated"],
                                      codec_frames=detail["codec_frames"],
                                      identity=detail["identity"])
                        done += 1
                        print(f"[{done}/{len(inputs)}] {ident_str} ok "
                              f"({record['wall_s']}s, {record['audio_seconds']:.1f}s audio"
                              f"{' TRUNCATED' if record['truncated'] else ''})", flush=True)
                    else:
                        record.update(status="finalize_failed", error=fin.stderr[-500:])
                        fail += 1
                        print(f"[FAIL-finalize] {ident_str}: {fin.stderr[-200:]}", flush=True)
                else:
                    if STOP.is_set() and not ok:
                        record.update(status="interrupted", error=err)
                    else:
                        record.update(status="generation_failed", error=err)
                    fail += 1
                    print(f"[FAIL] {ident_str}: {err}", flush=True)
                append(manifest_path, record)
    finally:
        mem = poller.stop()
    summary = {
        "run": str(args.runs), "run_id": run_id, "expected": len(inputs),
        "complete": done, "resumed": skipped, "failed": fail,
        "pending": len(inputs) - done - fail,
        "wall_s": round(time.time() - started, 1),
        "peak_vram_bytes": mem["peak_vram_bytes"],
        "peak_gtt_bytes": mem["peak_gtt_bytes"],
        "stopped_by_signal": STOP.is_set(),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    atomic_write(args.runs / "generation_summary.json",
                 json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if fail == 0 and done == len(inputs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
