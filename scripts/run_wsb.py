#!/usr/bin/env python3
"""run_wsb.py v2 - WSB generation driver: official protocol, hardened, portable.

Changes over v1 (mission Phase 6):
  - workspace from --workspace / YUE2_WORKSPACE (no hard-coded machine paths)
  - immutable run_config.json (platform, gpu, torch, sglang commit, dataset and
    model revisions, patchset hash, run_id); mismatch on resume -> abort
  - quarantine instead of delete for stale/partial candidate artifacts
  - disk-space safety check before each request
  - SIGINT/SIGTERM: graceful stop after the in-flight candidate; statuses journaled
  - VRAM/GTT polling via any renderD* node or rocm-smi (no hard-coded card1)
  - atomic manifest appends and evaluation_inputs.jsonl (write-once, verified on resume)
  - per-candidate status journal: generated/finalized/verified/failed/truncated/pending/retried

Official budgets are fixed constants - never reduced.
"""
from __future__ import annotations

import argparse
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

WS = Path(os.environ.get("YUE2_WORKSPACE",
                         Path(__file__).resolve().parents[2]))
MANIFEST = WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
MODEL_DIR = WS / "models/YuE2-3B"
VAE_DIR = WS / "models/YuE2-Vae-legacy"
FINALIZE = Path(__file__).resolve().parent / "finalize_candidate.py"

OFFICIAL = {
    "cot": "full", "abc": None,
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
    """VRAM/GTT/system sampling with dynamic device discovery."""

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

    def _read_rocm_smi(self) -> tuple[int, int]:
        try:
            out = subprocess.run(["rocm-smi", "--showmeminfo", "vram,gtt", "--csv"],
                                 capture_output=True, text=True, timeout=15).stdout
            vram = gtt = 0
            for line in out.splitlines():
                if line.startswith("card") and "," in line:
                    parts = [p.strip() for p in line.split(",")]
                    try:
                        val = int(parts[-1])
                    except ValueError:
                        continue
                    if len(parts) >= 3 and "gtt" in parts[1].lower():
                        gtt = max(gtt, val)
                    else:
                        vram = max(vram, val)
        except Exception:
            pass
        return vram, gtt

    def _run(self):
        while not self._stop.is_set():
            vram, gtt = self._read_sysfs()
            if vram == 0 and gtt == 0:
                vram, gtt = self._read_rocm_smi()
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


def post_generation(server: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        f"{server}/v1/audio/generations",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def candidate_complete(cand: Path) -> bool:
    try:
        sys.path.insert(0, str(WS / "benchmark" / "wsb_metrics"))
        from artifact_storage import verify_result
        verify_result(cand)
        return True
    except Exception:
        return False


def detect_platform() -> dict:
    ident = {
        "platform": os.environ.get("YUE2_PLATFORM", "unknown"),
        "gpu": os.environ.get("YUE2_GPU", "unknown"),
        "torch": os.environ.get("YUE2_TORCH", "unknown"),
    }
    try:
        out = subprocess.run(["rocm-smi", "--showproductname", "--csv"],
                             capture_output=True, text=True, timeout=15).stdout
        for line in out.splitlines():
            if "Card series" in line:
                ident["gpu"] = line.split(",", 1)[1].strip()
    except Exception:
        pass
    try:
        import torch  # noqa
        ident["torch"] = torch.__version__
        ident["platform"] = torch.cuda.get_device_properties(0).gcnArchName \
            if torch.cuda.is_available() else ident["platform"]
    except Exception:
        pass
    return ident


def patchset_hash() -> str:
    import hashlib
    p = Path(__file__).resolve().parent.parent / "patches"
    h = hashlib.sha256()
    for f in sorted(p.glob("*.patch")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def check_or_write_run_config(runs_dir: Path, ident: dict) -> int:
    """Write the immutable run identity; 3 on mismatch (never mix runs)."""
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
    """Write-once evaluation_inputs.jsonl; 3 on divergence."""
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
    ap.add_argument("--runs", type=Path, required=True,
                    help="run directory, e.g. runs/gfx1100/<run_id>/wsb_full")
    ap.add_argument("--indices", type=int, nargs="*", default=None,
                    help="prompt indices; default: all 192 (official full run)")
    ap.add_argument("--server", default=os.environ.get("SERVER", "http://127.0.0.1:31000"))
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--wav-archive", type=Path,
                    default=Path(os.environ.get("YUE2_WAV_ARCHIVE", "")) or None,
                    help="move per-candidate WAVs here after verified finalize "
                         "( FLAC is the official artifact; WAV is intermediate)")
    args = ap.parse_args()

    args.runs = args.runs.resolve()  # payloads embed absolute paths (server cwd differs)
    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    assert len(rows) == 192 and [r["prompt_index"] for r in rows] == list(range(192)), \
        "frozen manifest shape violated"
    selected = rows if args.indices is None else [r for r in rows
                                                  if r["prompt_index"] in args.indices]
    assert selected, "no manifest rows selected"

    songs = args.runs / "songs"
    songs.mkdir(parents=True, exist_ok=True)
    manifest_path = args.runs / "generation_manifest.jsonl"

    # ---- immutable run identity -------------------------------------------------
    run_id = args.run_id or time.strftime("run%Y%m%dT%H%M%SZ", time.gmtime())
    ident = detect_platform()
    ident.update({
        "run_id": run_id,
        "sglang_commit": "ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f",
        "dataset_revision": "e361b85a8d7365d3079fa9647641a87ce3c8c5b5",
        "model_revision": "m-a-p/YuE2-3B@1a96eca688d6ae5d7f0feb88573fec89920fcd19",
        "vae_revision": "m-a-p/YuE2-Vae-legacy@b54118f0fc462f08999d1ec07e88817f4ee3f770",
        "patchset_sha256": patchset_hash(),
        "config": OFFICIAL,
        "candidates": 2,
        "indices": None if args.indices is None else sorted(args.indices),
    })
    run_config_path = args.runs / "run_config.json"
    rc = check_or_write_run_config(args.runs, ident)
    if rc:
        return rc

    # ---- evaluation_inputs.jsonl (write-once, verify on resume) -----------------
    inputs = []
    for row in selected:
        for j, seed in enumerate(row["candidate_ar_seeds"][:2]):
            i = row["prompt_index"]
            ident_str = f"wsb_{i:03d}_r{j}_s{seed}"
            inputs.append({"prompt_index": i, "candidate_index": j,
                           "seed": seed, "path": f"songs/{ident_str}"})
    inputs_path = args.runs / "evaluation_inputs.jsonl"
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
                    # quarantine stale/partial artifacts - never delete evidence,
                    # never mix runs
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

                wav_name = f"{ident_str}.wav"
                payload = {
                    "style": row["style"], "lyrics": row["lyrics"],
                    "seed": seed, "output_path": str(songs),
                    "output_file_name": wav_name,
                    "artifacts_dir": str(cand), "id": ident_str, **OFFICIAL,
                }
                t0 = time.time()
                ok, err, retries = False, "", 0
                wav = None
                for attempt in range(args.max_retries + 1):
                    if STOP.is_set():
                        break
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
                        retries += 1
                        print(f"[retry {attempt}] {ident_str}: {err}", flush=True)
                        time.sleep(10)
                record["wall_s"] = round(time.time() - t0, 2)
                record["retries"] = retries

                if ok and wav is not None and wav.is_file():
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
                        if args.wav_archive:
                            # FLAC (official artifact) verified; archive the
                            # bulky intermediate WAV to large storage
                            arc = args.wav_archive / run_id
                            arc.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(wav), str(arc / wav_name))
                            record["wav_archived"] = str(arc / wav_name)
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
