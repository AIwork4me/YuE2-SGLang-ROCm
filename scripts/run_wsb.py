#!/usr/bin/env python3
"""WSB generation driver (pilot + full): official protocol, resumable, auditable.

Replaces the PR's embedded bash driver with configurable paths and
runtime-discovered server URL. For every manifest row and candidate j in 0..1:
  - request payload uses the row's ORIGINAL style/lyrics/seed (never rewritten)
  - official budgets: cot=full, cfg_scale=1.0, ode_steps=32,
    semantic_max_tokens=9000, abc_max_tokens=4096, vae_core_frames=1024,
    vae_halo_frames=16
  - artifacts_dir -> server exports the WSB bundle; finalize_candidate.py
    completes score.abc/audio.flac/config.json/result.json (official 0.1.3
    semantics, verified by wsb_metrics.artifact_storage.verify_result)
  - per-candidate status appended atomically to <runs>/generation_manifest.jsonl
  - resume: candidates whose result.json verifies complete are skipped

Usage:
  python scripts/run_wsb.py --runs runs/wsb_pilot --indices 0 1 2 3 4
  python scripts/run_wsb.py --runs runs/wsb_full            # all 192 prompts
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

WS = Path(os.environ.get("WS", "/home/amd/Desktop/YuE2"))
sys.path.insert(0, str(WS / "upstream" / "sglang" / "python"))
sys.path.insert(0, str(WS / "benchmark" / "WildSongBench" / "wsb_metrics"))

MANIFEST = WS / "benchmark" / "WildSongBench" / "benchmark" / "reproduction_manifest.jsonl"
MODEL_DIR = WS / "models" / "YuE2-3B"
VAE_DIR = WS / "models" / "YuE2-Vae-legacy"

# cfg_scale is deliberately NOT sent: Yue2SamplingParams at the PR head does
# not accept the key (the PR's embedded bash script predates the head), and
# SongRequest.guidance resolves cfg_scale=None with cot=full to exactly 1.0 —
# the single-branch configuration the official protocol uses.
OFFICIAL = {
    "cot": "full", "abc": None,
    "ode_steps": 32, "semantic_max_tokens": 9000, "abc_max_tokens": 4096,
    "vae_core_frames": 1024, "vae_halo_frames": 16,
}


class MemoryPoller:
    """Sample GTT/VRAM/system memory while generation runs."""

    def __init__(self, interval=5.0):
        self.interval = interval
        self.samples: list[dict] = []
        self.peak_gtt_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _read_gtt(self) -> int:
        try:
            for p in Path("/sys/class/drm/card1/device").glob("mem_info_gtt_used"):
                return int(p.read_text())
        except OSError:
            pass
        try:
            out = subprocess.run(["rocm-smi", "--showmeminfo", "gtt", "--csv"],
                                 capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                if line.startswith("card") and "," in line:
                    return int(line.split(",")[-1])
        except Exception:
            pass
        return 0

    def _run(self):
        while not self._stop.is_set():
            used = self._read_gtt()
            self.peak_gtt_bytes = max(self.peak_gtt_bytes, used)
            mem = {}
            for key in ("MemAvailable", "SwapFree"):
                try:
                    for line in Path("/proc/meminfo").read_text().splitlines():
                        if line.startswith(key):
                            mem[key] = int(line.split()[1])
                except OSError:
                    pass
            self.samples.append({"t": round(time.time(), 1), "gtt_used": used, **mem})
            self._stop.wait(self.interval)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=15)
        return {"peak_gtt_bytes": self.peak_gtt_bytes,
                "samples": len(self.samples)}


def post_generation(server: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        f"{server}/v1/audio/generations",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def candidate_complete(cand: Path) -> bool:
    try:
        from artifact_storage import verify_result

        verify_result(cand)
        return True
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--indices", type=int, nargs="*", default=None,
                    help="prompt indices; default: all")
    ap.add_argument("--candidates", type=int, default=2, choices=(2, 8))
    ap.add_argument("--server", default=os.environ.get("SERVER", "http://127.0.0.1:30065"))
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--max-retries", type=int, default=2)
    args = ap.parse_args()

    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    assert len(rows) == 192 and [r["prompt_index"] for r in rows] == list(range(192))
    selected = rows if args.indices is None else [r for r in rows if r["prompt_index"] in args.indices]
    assert selected, "no manifest rows selected"

    songs = args.runs / "songs"
    songs.mkdir(parents=True, exist_ok=True)
    manifest_path = args.runs / "generation_manifest.jsonl"

    # evaluation_inputs.jsonl (static, format expected by wsb_eval.py score)
    inputs = []
    for row in selected:
        for j, seed in enumerate(row["candidate_ar_seeds"][:args.candidates]):
            ident = f"wsb_{row['prompt_index']:03d}_r{j}_s{seed}"
            inputs.append({"prompt_index": row["prompt_index"], "candidate_index": j,
                           "seed": seed, "path": f"songs/{ident}"})
    (args.runs / "evaluation_inputs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in inputs))

    poller = MemoryPoller().start()
    started = time.time()
    done = fail = 0
    try:
        for row in selected:
            for j, seed in enumerate(row["candidate_ar_seeds"][:args.candidates]):
                i = row["prompt_index"]
                ident = f"wsb_{i:03d}_r{j}_s{seed}"
                cand = songs / ident
                record = {"id": ident, "prompt_index": i, "candidate_index": j,
                          "seed": seed, "source": "m-a-p/WildSongBench@e361b85a",
                          "sglang": "ced0ef7d + patches 0001-0005",
                          "model": "m-a-p/YuE2-3B@1a96eca6",
                          "vae": "m-a-p/YuE2-Vae-legacy@b54118f",
                          "config": OFFICIAL}
                if candidate_complete(cand):
                    record["status"] = "complete(resumed)"
                    append(manifest_path, record)
                    done += 1
                    print(f"[skip] {ident} already complete", flush=True)
                    continue

                if cand.exists():
                    import shutil
                    shutil.rmtree(cand)  # stale/partial: never mix runs
                # Per-candidate WAV name: a shared name would let a later
                # request overwrite an earlier candidate's audio before
                # finalization.
                wav_name = f"{ident}.wav"
                payload = {
                    "style": row["style"], "lyrics": row["lyrics"],
                    "seed": seed, "output_path": str(songs),
                    "output_file_name": wav_name,
                    "artifacts_dir": str(cand), "id": ident, **OFFICIAL,
                }
                t0 = time.time()
                ok, err = False, ""
                wav = None
                for attempt in range(args.max_retries + 1):
                    try:
                        resp = post_generation(args.server, payload, args.timeout)
                        audio_field = resp.get("audio") or ""
                        wav = (songs / wav_name) if audio_field else None
                        ok = wav is not None and wav.is_file()
                        if not ok:
                            err = f"unexpected response: {str(resp)[:300]}"
                        break
                    except (urllib.error.URLError, TimeoutError, OSError) as exc:
                        err = f"{type(exc).__name__}: {exc}"
                        print(f"[retry {attempt}] {ident}: {err}", flush=True)
                        time.sleep(10)
                record["wall_s"] = round(time.time() - t0, 2)

                if ok and wav is not None and wav.is_file():
                    fin = subprocess.run(
                        [sys.executable, str(WS / "scripts" / "finalize_candidate.py"),
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
                        print(f"[{done}/{len(inputs)}] {ident} ok "
                              f"({record['wall_s']}s, {record['audio_seconds']:.1f}s audio)",
                              flush=True)
                    else:
                        record.update(status="finalize_failed", error=fin.stderr[-500:])
                        fail += 1
                        print(f"[FAIL-finalize] {ident}: {fin.stderr[-200:]}", flush=True)
                else:
                    record.update(status="generation_failed", error=err)
                    fail += 1
                    print(f"[FAIL] {ident}: {err}", flush=True)
                append(manifest_path, record)
    finally:
        mem = poller.stop()
    summary = {
        "run": str(args.runs), "expected": len(inputs), "complete": done,
        "failed": fail, "pending": len(inputs) - done - fail,
        "wall_s": round(time.time() - started, 1),
        "peak_gtt_bytes": mem["peak_gtt_bytes"],
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (args.runs / "generation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if fail == 0 and done == len(inputs) else 1


def append(path: Path, record: dict):
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
