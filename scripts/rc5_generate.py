#!/usr/bin/env python3
"""rc5_generate.py — RC5 campaign driver (ARM_B_LATEST_UPSTREAM_RC5).

Drives the FROZEN official WildSongBench protocol against the SGLang YuE2
server owned by scripts/gpu_lifecycle.py:

    prompts = 192 x 2 candidates = 384, seeds from the official manifest
    cot=full, cfg 1.0, ode_steps=32, semantic_max_tokens=9000,
    abc_max_tokens=4096, vae_core_frames=1024, vae_halo_frames=16
    Benchmark VAE = YuE2-Vae-legacy (never a listening-test VAE)

Official budgets are constants. Nothing here can lower them.

Per candidate (RC5 M4.2 / M0.3):
    launched receipt  -> request -> finalize -> official verify -> fsync
    -> atomic no-clobber publish (rename of a fully validated staging dir)
    -> result receipt in the crash-durable journal -> external checkpoint
A verified candidate is never overwritten; a damaged one is quarantined
(moved, never deleted) and regenerated with a higher attempt number.

Every N complete candidates an incremental checkpoint (tar.zst + SHA256
manifest) is written and, when --backup-dir is given, copied and re-verified
(size + SHA256). At the milestone counts a FULL restore manifest is written.

Exit codes: 0 all complete · 1 incomplete/failed · 2 server unusable
(the lifecycle supervisor then stops it; a relaunch resumes).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OFFICIAL = {
    "cot": "full", "abc": None,
    "ode_steps": 32, "semantic_max_tokens": 9000, "abc_max_tokens": 4096,
    "vae_core_frames": 1024, "vae_halo_frames": 16,
}
DATASET_REVISION = "e361b85a8d7365d3079fa9647641a87ce3c8c5b5"
DATASET_MANIFEST_SHA = "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0"
MODEL_REVISION = "m-a-p/YuE2-3B@1a96eca688d6ae5d7f0feb88573fec89920fcd19"
VAE_REVISION = "m-a-p/YuE2-Vae-legacy@b54118f0fc462f08999d1ec07e88817f4ee3f770"
MILESTONES = (32, 64, 128, 192, 256, 384)
STOP = threading.Event()


# ------------------------------------------------------------------ utils
def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def blob_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_durable(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        f.write(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def append_journal(path: Path, record: dict) -> None:
    """One line, flushed and fsynced BEFORE the caller proceeds: a crash can
    never leave a published candidate without its receipt or vice versa."""
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def bundle_hashes(cand: Path) -> dict:
    return {str(p.relative_to(cand)): {"sha256": sha256_file(p), "bytes": p.stat().st_size}
            for p in sorted(cand.rglob("*")) if p.is_file()}


def _git(tree: Path, *argv: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(tree), *argv], capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def read_json(p: Path):
    return json.loads(Path(p).read_text())


# ------------------------------------------------------- official verifier
def load_official_verifier(ws: Path):
    for p in (ws / "benchmark/WildSongBench/wsb_metrics",
              ws / "benchmark/wsb_metrics",
              ws / "benchmark/WildSongBench/evaluation/wsb_metrics"):
        if (p / "artifact_storage.py").is_file():
            sys.path.insert(0, str(p))
            from artifact_storage import verify_result  # official frozen checker
            return verify_result, str(p / "artifact_storage.py")
    raise RuntimeError("official evaluator bundle not found under the workspace")


# -------------------------------------------------------------- memory
class DeviceSampler:
    """VRAM/GTT/GPU-busy of ONE device (the bound drm card) — never a max
    over every card the host happens to expose through sysfs."""

    def __init__(self, card: str | None, sys_root: str = "/sys"):
        self.base = Path(sys_root) / "class/drm" / card / "device" if card else None
        self.peak_vram = self.peak_gtt = 0
        self.cur_vram = self.cur_gtt = 0
        self.gpu_busy_sum = self.gpu_busy_n = 0
        self.cpu_sum = self.cpu_n = 0
        self._mark = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.enabled = self.base is not None and (self.base / "mem_info_vram_used").is_file()

    def _cpu_ticks(self) -> int | None:
        try:
            parts = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
            vals = [int(x) for x in parts]
            return sum(vals[:8]), vals[3] + vals[4]
        except (OSError, ValueError, IndexError):
            return None

    def _read_int(self, name: str) -> int | None:
        try:
            return int((self.base / name).read_text().strip())
        except (OSError, ValueError):
            return None

    def _run(self):
        prev = self._cpu_ticks()
        while not self._stop.is_set():
            if self.enabled:
                v, g = self._read_int("mem_info_vram_used"), self._read_int("mem_info_gtt_used")
                b = self._read_int("gpu_busy_percent")
                if v is not None:
                    self.cur_vram = v
                    self.peak_vram = max(self.peak_vram, v)
                if g is not None:
                    self.cur_gtt = g
                    self.peak_gtt = max(self.peak_gtt, g)
                if b is not None:
                    self.gpu_busy_sum += b
                    self.gpu_busy_n += 1
            cur = self._cpu_ticks()
            if prev and cur and cur[0] > prev[0]:
                total = cur[0] - prev[0]
                idle = cur[1] - prev[1]
                self.cpu_sum += 100.0 * (total - idle) / total
                self.cpu_n += 1
            prev = cur
            self._stop.wait(1.0)

    def start(self):
        self._thread.start()
        return self

    def stop(self) -> dict:
        self._stop.set()
        self._thread.join(timeout=10)
        return self.totals()

    def mark(self):
        """Record the idle level; since_mark() = peak above that level."""
        self._mark = (self.cur_vram, self.cur_gtt)

    def since_mark(self) -> tuple[int | None, int | None]:
        if not self.enabled:
            return None, None
        v0, g0 = self._mark or (0, 0)
        return self.peak_vram - v0, self.peak_gtt - g0

    def totals(self) -> dict:
        return {"peak_vram_bytes": self.peak_vram if self.enabled else None,
                "peak_gtt_bytes": self.peak_gtt if self.enabled else None,
                "gpu_busy_percent_mean": round(self.gpu_busy_sum / self.gpu_busy_n, 2)
                if self.gpu_busy_n else None,
                "cpu_busy_percent_mean": round(self.cpu_sum / self.cpu_n, 2)
                if self.cpu_n else None,
                "sampling_device": str(self.base) if self.base else None}


# ---------------------------------------------------- server log facts
STAGE_RE = re.compile(r"\[(Yue2\w+Stage)\] finished in ([\d.]+) seconds")


def server_stage_timing(log: Path | None) -> dict | None:
    """Exact per-stage seconds of the LAST request from the server log
    (AR / NAR / artifact export / VAE decode), or None when unavailable."""
    if not log or not Path(log).is_file():
        return None
    with open(log, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 400_000))
        data = f.read().decode(errors="replace")
    idx = data.rfind("Running pipeline stages:")
    if idx < 0:
        return None
    out = {}
    for name, secs in STAGE_RE.findall(data[idx:]):
        out[name] = round(float(secs), 3)
    return out or None


def server_runtime_header(log: Path | None) -> dict:
    """What the SERVER process itself reported at boot: its sglang import
    path and capability flags (the driver's own import path proves nothing
    about the server)."""
    out = {"log": str(log) if log else None}
    if not log or not Path(log).is_file():
        out["available"] = False
        return out
    head = Path(log).read_bytes()[-100_000:].decode(errors="replace")
    starts = [m.start() for m in re.finditer(r"=== serve_yue2", head)]
    block = head[starts[-1]:] if starts else ""
    m = re.search(r"sglang_import=(\S+)", block)
    out["sglang_import_path"] = m.group(1) if m and m.group(1).startswith("/") else None
    m = re.search(r"flags: (.*)", block)
    out["flags"] = m.group(1).strip() if m else None
    out["vae_dir_env"] = (re.search(r"SGLANG_YUE2_VAE_DIR=(\S+)", block) or [None, None])[1]
    out["available"] = bool(block)
    return out


# -------------------------------------------------------------- identity
def runtime_identity() -> dict:
    """Identity of the code that REALLY generates: the imported SGLang."""
    import torch
    import sglang
    import sglang.srt.models.yue2 as yue2_pkg
    import sglang.multimodal_gen.runtime.pipelines_core.stages.model_specific_stages.yue2 as stage_pkg
    yue2_dir = Path(yue2_pkg.__file__).resolve().parent
    stage_dir = Path(stage_pkg.__file__).resolve().parent
    sglang_file = Path(sglang.__file__).resolve()
    tree = sglang_file.parent.parent          # <tree>/python/sglang/__init__.py
    diff = subprocess.run(["git", "-C", str(tree), "diff", "HEAD"], capture_output=True) \
        if _git(tree, "rev-parse", "HEAD") is not None else None
    return {
        "torch_version": torch.__version__, "torch_hip": torch.version.hip,
        "sglang_import_path": str(sglang_file),
        "sglang_tree": str(tree),
        "sglang_commit": _git(tree, "rev-parse", "HEAD"),
        "sglang_tracked_diff_sha256": hashlib.sha256(diff.stdout).hexdigest()
        if diff is not None and diff.stdout else None,
        "sglang_untracked_in_package": _git(tree, "status", "--porcelain", "--untracked-files=all", "--", "python")
        or "",
        "yue2_runtime_sha256": blob_sha({p.name: sha256_file(p)
                                         for p in sorted(yue2_dir.glob("*.py"))}),
        "yue2_stages_sha256": blob_sha({p.name: sha256_file(p)
                                        for p in sorted(stage_dir.glob("*.py"))}),
    }


def environment_hash(python: str) -> str | None:
    try:
        r = subprocess.run([python, "-m", "pip", "freeze", "--all"],
                           capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return hashlib.sha256(r.stdout.encode()).hexdigest() if r.returncode == 0 else None


# --------------------------------------------------------------- driver
class Campaign:
    def __init__(self, a):
        self.a = a
        self.run_dir = a.run_dir.resolve()
        self.songs = self.run_dir / "songs"
        self.wavs = self.run_dir / "wavs"
        self.staging = self.run_dir / "staging"
        self.checkpoints = self.run_dir / "checkpoints"
        self.journal = self.run_dir / "journal.jsonl"
        self.progress = self.run_dir / "progress.json"
        self.verify_result, self.verifier_path = load_official_verifier(a.workspace)
        self.manifest = a.workspace / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
        self.manifest_sha = sha256_file(self.manifest)
        self.model_dir = a.workspace / "models/YuE2-3B"
        self.vae_dir = a.workspace / "models/YuE2-Vae-legacy"
        self.complete: set[str] = set()
        self.failed: dict[str, str] = {}
        self.perf: list[dict] = []
        self.checkpointed: set[str] = set()
        self.attempts: dict[str, int] = {}
        self.t0 = time.time()
        self.sampler = None
        self.milestones_done: set[int] = set()

    # -------------------------------------------------------------- setup
    def event(self, name: str, **rec) -> dict:
        rec = {"event": name, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "run_id": self.a.run_id, **rec}
        append_journal(self.journal, rec)
        self.touch_progress()
        return rec

    def touch_progress(self) -> None:
        tmp = self.progress.with_name("progress.json.tmp")
        tmp.write_text(json.dumps({"run_id": self.a.run_id, "complete": len(self.complete),
                                   "failed": len(self.failed),
                                   "expected": len(self.rows_selected) * 2,
                                   "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
        os.replace(tmp, self.progress)

    def build_identity(self) -> dict:
        gpu = read_json(self.a.gpu_receipt) if self.a.gpu_receipt and Path(self.a.gpu_receipt).is_file() else {}
        srv = read_json(self.a.server_receipt) if self.a.server_receipt and Path(self.a.server_receipt).is_file() else {}
        ident = {
            "run_id": self.a.run_id,
            "arm": "ARM_B_LATEST_UPSTREAM_RC5",
            "driver_repo_head": _git(REPO, "rev-parse", "HEAD"),
            "driver_repo_dirty": bool(_git(REPO, "status", "--porcelain")),
            "driver_sha256": sha256_file(Path(__file__).resolve()),
            "runtime": runtime_identity(),
            "environment_freeze_sha256": environment_hash(sys.executable),
            "dataset_revision": DATASET_REVISION,
            "dataset_manifest_sha256": self.manifest_sha,
            "model_revision": MODEL_REVISION,
            "model_sha256": sha256_file(self.model_dir / "model.safetensors"),
            "vae_revision": VAE_REVISION,
            "vae_sha256": sha256_file(self.vae_dir / "model.safetensors"),
            "config": OFFICIAL,
            "candidates": 2,
            "indices": None if self.a.indices is None else sorted(self.a.indices),
            "gpu": {"name": (gpu.get("device") or {}).get("name"),
                    "arch": (gpu.get("device") or {}).get("gcn_arch_names"),
                    "pci_bdf": gpu.get("bound_bdf") or (gpu.get("device") or {}).get("pci_bdf"),
                    "uuid": (gpu.get("device") or {}).get("sysfs_unique_id"),
                    "drm_card": (gpu.get("device") or {}).get("drm_card"),
                    "identity_status": gpu.get("status"),
                    "identity_receipt": str(self.a.gpu_receipt) if self.a.gpu_receipt else None},
            "official_verifier_sha256": sha256_file(Path(self.verifier_path)),
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        # the SERVER identity is per launch, not per run: it belongs to the journal
        ident["server_identity_is_per_launch"] = True
        self.server = {k: srv.get(k) for k in ("pid", "uid", "starttime", "argv_sha256", "port")}
        if self.a.server_receipt:
            self.server["receipt"] = str(self.a.server_receipt)
            self.server["receipt_sha256"] = sha256_file(Path(self.a.server_receipt))
        # the SERVER's code identity comes from the server's own boot header
        hdr = server_runtime_header(self.a.server_log)
        self.server["runtime_header"] = hdr
        srv_path = hdr.get("sglang_import_path")
        own = ident["runtime"]["sglang_import_path"]
        consistent = srv_path is None or own is None or \
            Path(srv_path).resolve() == Path(own).resolve()
        self.server["import_path_consistent_with_driver"] = consistent
        if not consistent:
            print(f"FATAL: the serving process imports sglang from {srv_path} but this "
                  f"driver imports it from {own}: not the same code", flush=True)
        ident["server_log"] = str(self.a.server_log) if self.a.server_log else None
        return ident

    def setup(self) -> int:
        if self.manifest_sha != DATASET_MANIFEST_SHA:
            print(f"FATAL: dataset manifest sha {self.manifest_sha} != frozen pin")
            return 3
        self.rows = [json.loads(l) for l in self.manifest.read_text().splitlines() if l.strip()]
        if len(self.rows) != 192 or [r["prompt_index"] for r in self.rows] != list(range(192)):
            print("FATAL: frozen manifest shape violated")
            return 3
        self.rows_selected = self.rows if self.a.indices is None else [
            r for r in self.rows if r["prompt_index"] in set(self.a.indices)]
        if not self.rows_selected:
            print("FATAL: no manifest rows selected")
            return 2
        for d in (self.run_dir, self.songs, self.wavs, self.staging, self.checkpoints):
            d.mkdir(parents=True, exist_ok=True)
        ident = self.build_identity()
        if self.server.get("import_path_consistent_with_driver") is False:
            return 3   # never drive a server whose code differs from the audited tree
        cfg = self.run_dir / "run_config.json"
        if cfg.is_file():
            prev = read_json(cfg)
            # resume: every identity field must match except wall-clock metadata
            skip = {"driver_repo_dirty", "created_at_utc", "server_identity_is_per_launch"}
            drift = {k: (prev.get(k), ident.get(k)) for k in ident
                     if k not in skip and prev.get(k) != ident.get(k)}
            if drift:
                print("FATAL: run_config.json identity drift on resume (never mix runs): "
                      + ", ".join(sorted(drift)))
                for k in sorted(drift):
                    print(f"   {k}: {str(drift[k][0])[:80]} -> {str(drift[k][1])[:80]}")
                return 3
        else:
            write_json_durable(cfg, ident)
        self.ident = ident
        # evaluation_inputs.jsonl: write-once, byte-exact on resume
        inputs = []
        for row in self.rows_selected:
            for j, seed in enumerate(row["candidate_ar_seeds"][:2]):
                i = row["prompt_index"]
                inputs.append({"prompt_index": i, "candidate_index": j, "seed": seed,
                               "path": f"songs/wsb_{i:03d}_r{j}_s{seed}"})
        self.inputs = inputs
        want = "".join(json.dumps(r) + "\n" for r in inputs)
        ip = self.run_dir / "evaluation_inputs.jsonl"
        if ip.is_file():
            if ip.read_text() != want:
                print("FATAL: evaluation_inputs.jsonl differs from the selected set")
                return 3
        else:
            with open(ip, "w") as f:
                f.write(want)
                f.flush()
                os.fsync(f.fileno())
            fsync_dir(self.run_dir)
        self.event("launch", driver_pid=os.getpid(), server=self.server,
                   expected=len(inputs))
        return 0

    # -------------------------------------------------------------- resume
    def replay_journal(self) -> dict:
        """Rebuild in-memory counters from the durable journal so attempt
        numbers stay monotonic across relaunches. A torn last line (crash
        mid-write) is counted and skipped, never hidden."""
        torn = 0
        if self.journal.is_file():
            for line in self.journal.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    torn += 1
                    continue
                if e.get("event") == "launched" and e.get("id"):
                    self.attempts[e["id"]] = max(self.attempts.get(e["id"], 0),
                                                 int(e.get("attempt", 0)))
        self.torn_journal_lines = torn
        return {"replayed_attempts": dict(self.attempts), "torn_lines": torn}

    def audit_existing(self) -> dict:
        """Only missing or damaged candidates are (re)generated."""
        rep = self.replay_journal()
        self.event("journal_replayed", **rep)
        already, damaged, missing = [], [], []
        for e in self.inputs:
            cid = self.cid(e)
            cand = self.songs / cid
            if (cand / "result.json").is_file():
                try:
                    self.verify_result(cand)
                    req = read_json(cand / "request.json")
                    if req.get("seed") != e["seed"]:
                        raise ValueError(f"seed {req.get('seed')} != official {e['seed']}")
                    self.complete.add(cid)
                    already.append(cid)
                    continue
                except Exception as exc:  # noqa: BLE001 - any defect is damage
                    damaged.append({"id": cid, "error": f"{type(exc).__name__}: {exc}"[:300]})
            missing.append(cid)
        rec = self.event("resume_audit", complete_verified=len(already),
                         complete_ids=already, damaged=damaged, missing=missing)
        for d in damaged:
            self.quarantine(self.songs / d["id"], d["id"], reason=d["error"])
        # anything left in staging is debris of an interrupted attempt
        if self.staging.is_dir():
            for p in list(self.staging.iterdir()):
                if p.name.startswith("."):
                    continue
                self.quarantine(p, p.name, reason="staging debris of an interrupted attempt")
        return rec

    def quarantine(self, path: Path, cid: str, reason: str) -> None:
        q = self.run_dir / "quarantine" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        q.mkdir(parents=True, exist_ok=True)
        dest = q / path.name
        shutil.move(str(path), str(dest))
        fsync_dir(q.parent)
        self.event("quarantined", id=cid, from_=str(path), to=str(dest), reason=reason)

    @staticmethod
    def cid(e: dict) -> str:
        return f"wsb_{e['prompt_index']:03d}_r{e['candidate_index']}_s{e['seed']}"

    # -------------------------------------------------------------- checkpoint
    def checkpoint(self, kind: str, ids: list[str]) -> dict | None:
        n = len(self.complete)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        members = [self.journal, self.run_dir / "run_config.json", self.run_dir / "evaluation_inputs.jsonl"]
        if kind == "full":
            members += [self.songs / c for c in sorted(self.complete)]
            name = f"full-{n:03d}-{stamp}"
        else:
            members += [self.songs / c for c in sorted(set(ids) - self.checkpointed)]
            name = f"incremental-{n:03d}-{stamp}"
        manifest = {
            "kind": kind, "run_id": self.a.run_id, "complete_count": n,
            "created_at_utc": stamp,
            "run_config_sha256": sha256_file(self.run_dir / "run_config.json"),
            "evaluation_inputs_sha256": sha256_file(self.run_dir / "evaluation_inputs.jsonl"),
            "journal_sha256": sha256_file(self.journal),
            "candidates": {c: bundle_hashes(self.songs / c)
                           for c in sorted(self.complete)} if kind == "full" else
                          {c: bundle_hashes(self.songs / c)
                           for c in sorted(set(ids) - self.checkpointed)},
        }
        manifest_path = self.checkpoints / f"{name}.manifest.json"
        write_json_durable(manifest_path, manifest)
        tar_path = self.checkpoints / f"{name}.tar"
        with tarfile.open(tar_path, "w") as tf:
            for m in members:
                tf.add(m, arcname=m.name)
            tf.add(manifest_path, arcname=manifest_path.name)
        zst = tar_path.with_suffix(".tar.zst")
        r = subprocess.run(["zstd", "-q", "-T0", "-3", "--rm", str(tar_path), "-o", str(zst)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            zst = tar_path  # uncompressed fallback; still a valid checkpoint
        with open(zst, "rb") as f:
            os.fsync(f.fileno())
        fsync_dir(self.checkpoints)
        rec = self.event("checkpoint", kind=kind, complete_count=n,
                         archive=str(zst), bytes=zst.stat().st_size,
                         archive_sha256=sha256_file(zst),
                         manifest=str(manifest_path),
                         manifest_sha256=sha256_file(manifest_path),
                         candidate_ids=sorted(set(ids) - self.checkpointed))
        if kind != "full":
            self.checkpointed |= set(ids)
        if self.a.backup_dir:
            rec["backup"] = self.backup_verify(zst, manifest_path)
            append_journal(self.journal, {"event": "backup_verified", **rec["backup"]})
        if kind != "full" and n in MILESTONES:
            self.milestone(n)
        return rec

    def backup_verify(self, *files: Path) -> dict:
        """Copy to the backup destination and re-verify size + SHA256 there.
        The destination class is disclosed; a same-host copy is NEVER an
        off-machine backup."""
        dest_dir = Path(self.a.backup_dir) / "checkpoints" / self.a.run_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = {"destination": str(dest_dir), "class": self.a.backup_class, "files": {}}
        for f in files:
            d = dest_dir / f.name
            tmp = d.with_name(d.name + ".part")
            shutil.copyfile(f, tmp)
            with open(tmp, "rb") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp, d)
            size_ok = d.stat().st_size == f.stat().st_size
            sha_ok = sha256_file(d) == sha256_file(f)
            out["files"][f.name] = {"bytes": d.stat().st_size, "size_ok": size_ok,
                                    "sha256_ok": sha_ok}
            out["ok"] = size_ok and sha_ok
        return out

    def milestone(self, n: int) -> None:
        if n in self.milestones_done:
            return
        self.milestones_done.add(n)
        ids = sorted(self.complete)
        restore = {
            "schema": "yue2-rc5-restore-manifest/1", "run_id": self.a.run_id,
            "complete_count": n, "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_config_sha256": sha256_file(self.run_dir / "run_config.json"),
            "journal_sha256": sha256_file(self.journal),
            "models": {k: self.ident[k] for k in ("model_revision", "model_sha256",
                                                  "vae_revision", "vae_sha256", "dataset_revision",
                                                  "dataset_manifest_sha256")},
            "candidates": {c: {"audio_flac_sha256": h.get("audio.flac", {}).get("sha256"),
                               "identity": read_json(self.songs / c / "result.json").get("identity"),
                               "files": h}
                           for c in ids for h in [bundle_hashes(self.songs / c)]},
        }
        p = self.checkpoints / f"restore-manifest-{n:03d}.json"
        write_json_durable(p, restore)
        self.checkpoint("full", ids)
        self.event("milestone", n=n, restore_manifest=str(p),
                   restore_manifest_sha256=sha256_file(p))

    # -------------------------------------------------------------- generation
    def request(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.a.server}/v1/audio/generations",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.a.timeout) as resp:
            return json.loads(resp.read())

    def server_state(self) -> str:
        if not self.a.server_receipt:
            return "UNKNOWN(no receipt)"
        try:
            r = subprocess.run(
                [sys.executable, str(REPO / "scripts/server_readiness.py"), "check",
                 "--receipt", self.a.server_receipt, "--url", self.a.server,
                 "--expect-model-path", str(self.model_dir)],
                capture_output=True, text=True, timeout=120)
            for line in r.stdout.splitlines()[::-1]:
                try:
                    return json.loads(line).get("state") or "UNKNOWN"
                except ValueError:
                    continue
        except (OSError, subprocess.TimeoutExpired):
            pass
        return "UNKNOWN"

    def generate(self, e: dict) -> dict:
        cid = self.cid(e)
        row = self.rows[e["prompt_index"]]
        attempt = self.attempts.get(cid, 0) + 1
        self.attempts[cid] = attempt
        payload = {"style": row["style"], "lyrics": row["lyrics"], "seed": e["seed"],
                   **OFFICIAL}
        work = self.staging / f"{cid}.attempt-{attempt}"
        if work.exists():
            shutil.rmtree(work)
        cand = work / cid
        work.mkdir(parents=True)
        req_payload = {**payload, "output_path": str(work), "output_file_name": f"{cid}.wav",
                       "artifacts_dir": str(cand), "id": cid}
        prov = {"id": cid, "prompt_index": e["prompt_index"],
                "candidate_index": e["candidate_index"], "seed": e["seed"],
                "attempt": attempt,
                "style_sha256": sha_text(row["style"]),
                "lyrics_sha256": sha_text(row["lyrics"]),
                "manifest_row_sha256": blob_sha(row),
                "payload_sha256": blob_sha(req_payload),
                "server": self.server,
                "runtime_sha256": self.ident["runtime"]["yue2_runtime_sha256"],
                "gpu": {k: self.ident["gpu"].get(k) for k in ("pci_bdf", "uuid", "arch")}}
        launched = self.event("launched", staging=str(work), **prov)
        self.sampler.mark()
        t0 = time.time()
        # the result receipt is self-contained (same provenance as `launched`)
        rec = {**prov, "launched_ts": launched["ts"]}
        wav = work / f"{cid}.wav"
        try:
            resp = self.request(req_payload)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            state = self.server_state()
            answered = isinstance(exc, urllib.error.HTTPError)  # server replied
            rec.update(status="interrupted" if STOP.is_set() else "generation_failed",
                       error=f"{type(exc).__name__}: {exc}"[:400],
                       wall_s=round(time.time() - t0, 2), server_state_after=state,
                       server_answered=answered)
            self.quarantine(work, work.name, reason=rec["error"])
            # When is the server unusable (restart through the supervisor)?
            #   worker dead / process gone            -> always
            #   client timeout with a hung request     -> always
            #   connection-level failure + UNKNOWN liveness with a receipt on file
            # An HTTP error reply from a live, READY server is transient: the
            # candidate is retried in a later sweep instead of restarting.
            rec["server_unusable"] = (
                state in ("WORKER_DEAD", "STOPPED")
                or isinstance(exc, TimeoutError)
                or (not answered and state.startswith("UNKNOWN") and bool(self.a.server_receipt)))
            append_journal(self.journal, {"event": "result", **rec})
            return rec
        wall = time.time() - t0
        rec.update(wall_s=round(wall, 3), inference_time_s=resp.get("inference_time_s"),
                   peak_memory_mb=resp.get("peak_memory_mb"),
                   yue2_nar_fast=resp.get("yue2_nar_fast"))
        audio = resp.get("audio") or ""
        if not audio or not Path(audio).is_file() or not wav.is_file():
            rec.update(status="generation_failed", error=f"no audio in response: {str(resp)[:300]}")
            self.quarantine(work, work.name, reason=rec["error"])
            append_journal(self.journal, {"event": "result", **rec})
            return rec
        try:
            plan = read_json(cand / "plan.json")
        except (OSError, ValueError):
            plan = {}
        timing = plan.get("timing") or {}
        rec["stage_timing"] = timing
        rec["termination"] = {k: {"truncated": v.get("truncated"),
                                  "output_tokens": v.get("output_tokens"),
                                  "execution": v.get("execution"),
                                  "attention": v.get("attention"),
                                  "sampler": v.get("sampler")}
                              for k, v in timing.items() if isinstance(v, dict)}
        rec["ar_seconds"] = timing.get("total_seconds")
        rec["nar_vae_seconds_residual"] = (round(wall - timing["total_seconds"], 3)
                                           if isinstance(timing.get("total_seconds"), (int, float)) else None)
        # exact server-side stage durations of THIS request
        st = server_stage_timing(self.a.server_log) or {}
        rec["stage_seconds_server"] = st
        rec["nar_seconds"] = st.get("Yue2NARStage")
        rec["vae_seconds"] = st.get("Yue2VAEDecodeStage")
        rec["ar_stage_seconds_server"] = st.get("Yue2ARStage")
        # finalize under the SAME interpreter stack that serves (sglang importable)
        fin = subprocess.run(
            [sys.executable, str(REPO / "scripts/finalize_candidate.py"),
             str(cand), str(wav), str(self.model_dir), str(self.vae_dir)],
            capture_output=True, text=True,
            env={**os.environ, "YUE2_WORKSPACE": str(self.a.workspace)})
        if fin.returncode != 0:
            rec.update(status="finalize_failed",
                       error=f"rc={fin.returncode} {fin.stderr[-600:]}")
            self.quarantine(work, work.name, reason=rec["error"])
            append_journal(self.journal, {"event": "result", **rec})
            return rec
        try:
            self.verify_result(cand)
        except Exception as exc:  # noqa: BLE001
            rec.update(status="finalize_failed", error=f"official verify: {type(exc).__name__}: {exc}"[:400])
            self.quarantine(work, work.name, reason=rec["error"])
            append_journal(self.journal, {"event": "result", **rec})
            return rec
        detail = json.loads(fin.stdout)
        # ---- publish: fsync the validated bundle, then an atomic no-clobber rename
        for p in sorted(cand.rglob("*")):
            if p.is_file():
                with open(p, "rb") as fh:
                    os.fsync(fh.fileno())
        fsync_dir(cand)
        target = self.songs / cid
        if target.exists():  # never overwrite a published candidate
            self.quarantine(target, cid, reason="published dir present for an unverified id")
        os.rename(cand, target)
        fsync_dir(self.songs)
        wdest = self.wavs / f"{cid}.wav"
        if wdest.exists():
            self.quarantine(wdest, wdest.name, reason="superseded intermediate WAV")
        os.replace(wav, wdest)
        fsync_dir(self.wavs)
        hashes = bundle_hashes(target)
        pv, pg = self.sampler.since_mark()
        rec.update(
            status="complete", identity=detail["identity"],
            audio_seconds=detail["audio_seconds"], truncated=detail["truncated"],
            codec_frames=detail["codec_frames"],
            audio_flac_sha256=hashes["audio.flac"]["sha256"],
            wav_sha256=sha256_file(wdest), wav_bytes=wdest.stat().st_size,
            bundle_manifest_sha256=blob_sha(hashes), bundle_files=len(hashes),
            bundle_bytes=sum(h["bytes"] for h in hashes.values()),
            candidate_vram_delta_bytes=pv, candidate_gtt_delta_bytes=pg,
            flac_info=self._flac_info(target / "audio.flac"))
        rec["rtf"] = round(rec["wall_s"] / rec["audio_seconds"], 5)          # wall / audio
        rec["realtime_speed_multiplier"] = round(rec["audio_seconds"] / rec["wall_s"], 5)
        self.complete.add(cid)
        self.failed.pop(cid, None)
        shutil.rmtree(work, ignore_errors=True)
        append_journal(self.journal, {"event": "result", **rec})
        self.perf.append(rec)
        return rec

    @staticmethod
    def _flac_info(path: Path) -> dict | None:
        try:
            import soundfile as sf
            i = sf.info(str(path))
            return {"samplerate": int(i.samplerate), "channels": int(i.channels),
                    "frames": int(i.frames), "subtype": str(i.subtype)}
        except Exception:  # noqa: BLE001 - recorded as unknown, never invented
            return None

    # -------------------------------------------------------------- main loop
    def run(self) -> int:
        rc = self.setup()
        if rc:
            return rc
        self.audit_existing()
        gpu_card = (self.ident.get("gpu") or {}).get("drm_card")
        self.sampler = DeviceSampler(gpu_card).start()
        server_unusable = False
        pending = [e for e in self.inputs if self.cid(e) not in self.complete]
        print(f"[rc5] run_id={self.a.run_id} expected={len(self.inputs)} "
              f"already_complete={len(self.complete)} to_generate={len(pending)}", flush=True)
        for sweep in range(self.a.sweeps + 1):
            todo = [e for e in self.inputs if self.cid(e) not in self.complete]
            if sweep and not STOP.is_set() and todo:
                print(f"[rc5] sweep {sweep}: retrying {len(todo)} candidate(s)", flush=True)
            new_ids = []
            for e in todo:
                if STOP.is_set():
                    break
                cid = self.cid(e)
                free = shutil.disk_usage(self.run_dir).free / 2**30
                if free < self.a.min_free_gb:
                    self.event("disk_guard_stop", free_gib=round(free, 2))
                    STOP.set()
                    break
                res = self.generate(e)
                if res["status"] == "complete":
                    new_ids.append(cid)
                    print(f"[rc5] {len(self.complete)}/{len(self.inputs)} {cid} ok "
                          f"wall={res['wall_s']}s audio={res['audio_seconds']:.1f}s "
                          f"truncated={res['truncated']}", flush=True)
                else:
                    self.failed[cid] = res.get("error", res["status"])
                    print(f"[rc5] FAIL {cid} attempt={res['attempt']} "
                          f"{res['status']}: {res.get('error', '')[:160]}", flush=True)
                    if res.get("server_unusable"):
                        print(f"[rc5] server unusable ({res.get('server_state_after')}); "
                              "stopping the campaign for a supervised relaunch", flush=True)
                        server_unusable = True
                        break
                if len(new_ids) >= self.a.checkpoint_every:
                    self.checkpoint("incremental", new_ids)
                    new_ids = []
            if new_ids and not STOP.is_set():
                self.checkpoint("incremental", new_ids)
                new_ids = []
            if server_unusable or STOP.is_set() or not todo:
                break
        mem = self.sampler.stop()
        summary = self.summarize(mem, server_unusable)
        write_json_durable(self.run_dir / "generation_summary.json", summary)
        self.event("summary", **{k: summary[k] for k in ("complete", "failed", "expected",
                                                         "stopped_by_signal", "server_unusable")})
        print(json.dumps({k: summary[k] for k in ("expected", "complete", "failed",
                                                  "wall_s", "stopped_by_signal",
                                                  "server_unusable")}, indent=1))
        if summary["complete"] == summary["expected"]:
            self.milestone(summary["complete"])
            return 0
        return 2 if server_unusable else 1

    def summarize(self, mem: dict, server_unusable: bool) -> dict:
        walls = sorted(r["wall_s"] for r in self.perf)

        def pct(ps):
            if not walls:
                return None
            k = (len(walls) - 1) * ps
            f, c = int(k), min(int(k) + 1, len(walls) - 1)
            return round(walls[f] + (walls[c] - walls[f]) * (k - f), 2)
        stage = [k for k in ("abc", "semantic") if any(k in r.get("stage_timing", {}) for r in self.perf)]
        return {
            "run_id": self.a.run_id, "arm": "ARM_B_LATEST_UPSTREAM_RC5",
            "run": str(self.run_dir), "expected": len(self.inputs),
            "complete": len(self.complete),
            "complete_ids": sorted(self.complete),
            "failed": {k: v for k, v in sorted(self.failed.items()) if k not in self.complete},
            "generated_this_launch": len(self.perf),
            "wall_s": round(time.time() - self.t0, 1),
            "latency_s": {"n": len(walls), "p50": pct(0.50), "p90": pct(0.90),
                          "p95": pct(0.95), "p99": pct(0.99),
                          "min": walls[0] if walls else None,
                          "max": walls[-1] if walls else None,
                          "method": "linear interpolation over this launch's candidates"},
            "ar_stage_seconds_mean": {k: round(sum(r["stage_timing"][k].get("seconds", 0)
                                                   for r in self.perf if k in r.get("stage_timing", {}))
                                               / max(1, sum(1 for r in self.perf if k in r.get("stage_timing", {}))), 2)
                                      for k in stage},
            "nar_vae_residual_seconds_mean": round(sum(
                r["nar_vae_seconds_residual"] for r in self.perf
                if r.get("nar_vae_seconds_residual") is not None) /
                max(1, sum(1 for r in self.perf if r.get("nar_vae_seconds_residual") is not None)), 2)
            if self.perf else None,
            "audio_seconds_total": round(sum(r["audio_seconds"] for r in self.perf), 1),
            "audio_seconds_mean": round(sum(r["audio_seconds"] for r in self.perf) / len(self.perf), 2)
            if self.perf else None,
            "truncated_but_complete": sum(1 for r in self.perf if r["truncated"]),
            "attempts_total": sum(self.attempts.values()),
            "retries": sum(self.attempts.values()) - len(self.attempts),
            "memory": mem,
            "stopped_by_signal": STOP.is_set(), "server_unusable": server_unusable,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:31000")
    ap.add_argument("--indices", type=int, nargs="*", default=None,
                    help="prompt indices; default = all 192 (official full run)")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--sweeps", type=int, default=2,
                    help="extra passes over candidates that are not complete")
    ap.add_argument("--checkpoint-every", type=int, default=16)
    ap.add_argument("--backup-dir", type=Path, default=None)
    ap.add_argument("--backup-class", default="UNSPECIFIED",
                    help="disclosed destination class, e.g. same_host_second_volume")
    ap.add_argument("--min-free-gb", type=float, default=20.0)
    ap.add_argument("--gpu-receipt", type=Path, default=None)
    ap.add_argument("--server-receipt", type=Path, default=None)
    ap.add_argument("--server-log", type=Path, default=None,
                    help="the server's log file (exact stage timings, boot header)")
    a = ap.parse_args()

    def on_signal(signum, _frame):
        if not STOP.is_set():
            STOP.set()
            print(f"\n[rc5] signal {signum}: finishing the in-flight candidate, then exiting",
                  flush=True)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    return Campaign(a).run()


if __name__ == "__main__":
    raise SystemExit(main())
