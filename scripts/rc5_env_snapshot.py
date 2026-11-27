#!/usr/bin/env python3
"""rc5_env_snapshot.py — machine-readable environment + storage evidence (RC5 M0).

Collects the facts the mission requires for G0 (physical W7900 environment)
and for the disaster-recovery plan, without ever recording a secret:

  * OS / kernel / glibc, CPU, cgroup memory+cpu limits, swap
  * every GPU visible to THIS container: name, gfx arch, PCI BDF, UUID,
    VRAM in bytes / GiB / decimal GB, drm render node, KFD node, driver
  * ROCm userspace + torch stack (from the interpreter that runs the script)
  * /dev/kfd, /dev/dri, amdgpu kernel module version
  * build tool versions (python, gcc, cmake, ninja, git, gh, uv, ffmpeg)
  * mounts with their backing device (overlay snapshot vs real volume),
    free space and inodes
  * network reachability of every download source (status codes only)
  * presence — NAMES ONLY — of off-machine backup configuration

Usage: python scripts/rc5_env_snapshot.py [--out reports/w7900_rc5/00_ENVIRONMENT.json]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _run(cmd: list[str], timeout: float = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, f"{type(e).__name__}: {e}"


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _tool_version(cmd: list[str], pattern: str | None = None) -> str | None:
    rc, out = _run(cmd, timeout=20)
    if rc != 0 and not out:
        return None
    first = out.splitlines()[0] if out else ""
    if pattern:
        m = re.search(pattern, out)
        return m.group(0) if m else first[:120]
    return first[:160]


def os_facts() -> dict:
    rel = {}
    for line in (_read("/etc/os-release") or "").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            rel[k] = v.strip('"')
    rc, glibc = _run(["ldd", "--version"])
    rc, uptime = _run(["uptime", "-p"])
    return {
        "hostname": platform.node(),
        "os_pretty": rel.get("PRETTY_NAME"),
        "os_version_id": rel.get("VERSION_ID"),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "glibc": (glibc.splitlines()[0] if glibc else None),
        "uptime": uptime,
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def cpu_facts() -> dict:
    model, n = None, os.cpu_count()
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    return {"model": model, "logical_cpus_visible": n,
            "cgroup_cpu_max": _read("/sys/fs/cgroup/cpu.max"),
            "cgroup_cpuset": _read("/sys/fs/cgroup/cpuset.cpus.effective")}


def memory_facts() -> dict:
    def gib(v: str | None) -> float | None:
        try:
            return round(int(v) / 2**30, 2)
        except (TypeError, ValueError):
            return None
    info = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        k, _, v = line.partition(":")
        if k in ("MemTotal", "MemAvailable", "SwapTotal"):
            info[k] = int(v.split()[0]) * 1024
    return {
        "host_mem_total_gib": gib(info.get("MemTotal")),
        "cgroup_memory_max_bytes": _read("/sys/fs/cgroup/memory.max"),
        "cgroup_memory_max_gib": gib(_read("/sys/fs/cgroup/memory.max")),
        "cgroup_memory_current_bytes": _read("/sys/fs/cgroup/memory.current"),
        "cgroup_memory_swap_max_bytes": _read("/sys/fs/cgroup/memory.swap.max"),
        "cgroup_pids_max": _read("/sys/fs/cgroup/pids.max"),
        "note": "the cgroup limit (not the host total) bounds CPU offload",
    }


def gpu_facts() -> dict:
    out = {"amd_smi": None, "torch": None, "devices": [], "kernel": {}}
    out["kernel"] = {
        "amdgpu_module_version": _read("/sys/module/amdgpu/version"),
        "dev_kfd_present": Path("/dev/kfd").exists(),
        "dev_dri_render_nodes": sorted(p.name for p in Path("/dev/dri").glob("renderD*")),
        "dev_dri_cards": sorted(p.name for p in Path("/dev/dri").glob("card*")),
    }
    rc, smi = _run(["amd-smi", "list"])
    if rc == 0:
        out["amd_smi"] = [ln.strip() for ln in smi.splitlines() if ln.strip()]
    try:
        import torch
        out["torch"] = {"version": torch.__version__, "hip": torch.version.hip,
                        "cuda_build": torch.version.cuda,
                        "device_count": torch.cuda.device_count(),
                        "import_path": torch.__file__}
        for i in range(torch.cuda.device_count()):
            p = torch.cuda.get_device_properties(i)
            dom, bus, dev = (getattr(p, "pci_domain_id", None),
                             getattr(p, "pci_bus_id", None),
                             getattr(p, "pci_device_id", None))
            bdf = f"{dom:04x}:{bus:02x}:{dev:02x}.0" if None not in (dom, bus, dev) else None
            card = None
            for c in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
                real = os.path.realpath(c / "device")
                if bdf and real.endswith("/" + bdf):
                    card = c.name
            d = {"index": i, "name": p.name, "gcn_arch_name": p.gcnArchName,
                 "pci_bus_id": bus, "pci_domain_id": dom, "pci_device_id": dev,
                 "pci_bdf": bdf, "uuid": str(getattr(p, "uuid", "")),
                 "total_memory_bytes": p.total_memory,
                 "total_memory_gib": round(p.total_memory / 2**30, 2),
                 "total_memory_decimal_gb": round(p.total_memory / 1e9, 2),
                 "multi_processor_count": p.multi_processor_count,
                 "drm_card": card,
                 "vram_used_bytes_at_snapshot": int(_read(
                     f"/sys/class/drm/{card}/device/mem_info_vram_used") or 0) if card else None,
                 "gtt_total_bytes": int(_read(
                     f"/sys/class/drm/{card}/device/mem_info_gtt_total") or 0) if card else None,
                 "max_engine_clock_mhz": p.clock_rate // 1000 if getattr(p, "clock_rate", 0) else None,
                 "memory_clock_rate_mhz": p.memory_clock_rate // 1000 if getattr(p, "memory_clock_rate", 0) else None,
                 "vbios_version": _read(f"/sys/class/drm/{card}/device/vbios_version") if card else None,
                 }
            out["devices"].append(d)
    except Exception as e:  # noqa: BLE001 - recorded as a fact
        out["torch"] = {"error": f"{type(e).__name__}: {e}"}
    kfd = {}
    topo = Path("/sys/class/kfd/kfd/topology/nodes")
    if topo.is_dir():
        for node in sorted(topo.iterdir(), key=lambda p: p.name):
            f = node / "properties"
            try:
                kv = dict(ln.split(" ", 1) for ln in f.read_text().splitlines() if " " in ln)
            except OSError:
                kfd[node.name] = "UNREADABLE (outside this container)"
                continue
            if kv.get("vendor_id") == "4098":
                kfd[node.name] = {k: kv.get(k) for k in (
                    "device_id", "simd_count", "drm_render_minor", "max_engine_clk_fcompute",
                    "local_mem_size", "marketing_name", "gfx_target_version") if k in kv}
    out["kfd_gpu_nodes"] = kfd
    rc, rocminfo = _run(["rocminfo"])
    out["rocminfo_agents"] = re.findall(r"Marketing Name:\s+(.*)", rocminfo)
    out["rocminfo_isa"] = sorted(set(re.findall(r"amdgcn-amd-amdhsa--(gfx[\w-]+)", rocminfo)))
    m = re.search(r"ROCk module version (\S+)", rocminfo)
    out["rock_module_version"] = m.group(1) if m else None
    return out


def storage_facts() -> dict:
    out = {"mounts": [], "filesystems": []}
    rc, mounts = _run(["findmnt", "-J", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"])
    if rc == 0:
        try:
            for fs in json.loads(mounts).get("filesystems", []):
                fs.pop("children", None)  # keep the report small
                mountpoint = fs.pop("target", None)   # 'target' is a guarded key name
                if mountpoint in ("/", "/workspace", "/data", "/tmp", "/dev/shm") \
                        or str(mountpoint or "").startswith(("/data/yue2", "/workspace")):
                    fs["mountpoint"] = mountpoint
                    opts = fs.get("options", "")
                    fs["options"] = ",".join(o for o in opts.split(",") if not o.startswith("lowerdir="))
                    fs["upperdir"] = next((o.split("=", 1)[1][:160] for o in opts.split(",")
                                           if o.startswith("upperdir=")), None)
                    out["mounts"].append(fs)
        except ValueError:
            out["mounts_error"] = "unparsable findmnt output"
    for path in ("/", "/workspace", "/data", "/tmp"):
        if not Path(path).exists():
            continue
        u = shutil.disk_usage(path)
        out["filesystems"].append({
            "path": path, "total_bytes": u.total, "used_bytes": u.used,
            "free_bytes": u.free, "free_gib": round(u.free / 2**30, 2),
            "device": os.statvfs(path).f_fsid and _findmnt_source(path)})
    try:
        s = os.statvfs("/")
        out["inodes_root"] = {"total": s.f_files, "free": s.f_ffree}
    except OSError:
        pass
    out["block_devices"] = {}
    for b in sorted(Path("/sys/block").glob("*")):
        out["block_devices"][b.name] = {
            "rotational": _read(str(b / "queue/rotational")),
            "size_sectors": _read(str(b / "size")),
            "model": (_read(str(b / "device/model")) or "").strip(),
        }
    out["persistence_assessment"] = {
        "/": "container writable layer (containerd overlayfs snapshot) — tied to the "
             "container/image lifecycle",
        "/workspace": "loop-mounted ext4 volume provided by the platform (workspace "
                      "quota); survival across image deletion is NOT guaranteed by any "
                      "documented contract — verify by drill, do not assume",
    }
    return out


def _findmnt_source(path: str) -> str | None:
    rc, out = _run(["findmnt", "-n", "-o", "SOURCE,FSTYPE", "-T", path])
    return out or None


def network_facts() -> dict:
    import urllib.request
    urls = {
        "github_api": "https://api.github.com/",
        "github_git": "https://github.com/AIwork4me/YuE2-SGLang-ROCm/info/refs?service=git-upload-pack",
        "huggingface": "https://huggingface.co/api/datasets/m-a-p/WildSongBench",
        "hf_mirror": "https://hf-mirror.com/api/datasets/m-a-p/WildSongBench",
        "amd_wheel_index": "https://repo.amd.com/rocm/whl-multi-arch/torch/",
        "pytorch_wheel_index": "https://download.pytorch.org/whl/rocm7.14/torch/",
        "pypi": "https://pypi.org/simple/pytest/",
        "pypi_tuna": "https://pypi.tuna.tsinghua.edu.cn/simple/pytest/",
    }
    out = {"egress_proxy_configured": bool(os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")),
           "sources": {}}
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    for name, url in urls.items():
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "yue2-rc5-env/1"})
            with opener.open(req, timeout=20) as r:
                out["sources"][name] = {"url": url, "status": r.status,
                                        "seconds": round(time.monotonic() - t0, 2)}
        except urllib.error.HTTPError as e:
            out["sources"][name] = {"url": url, "status": e.code,
                                    "seconds": round(time.monotonic() - t0, 2)}
        except Exception as e:  # noqa: BLE001
            out["sources"][name] = {"url": url, "status": None,
                                    "error": type(e).__name__,
                                    "seconds": round(time.monotonic() - t0, 2)}
    return out


def backup_capability_facts() -> dict:
    """NAMES of possible off-machine backup configuration — never contents."""
    home = Path.home()
    candidates = {
        "rclone_conf": home / ".config/rclone/rclone.conf",
        "aws_credentials": home / ".aws/credentials",
        "aws_config_env": "AWS_ACCESS_KEY_ID" in os.environ,
        "gcloud_config_dir": home / ".config/gcloud",
        "azure_profile": home / ".azure",
        "ssh_private_key_config": home / ".ssh/config",
        "gcp_default_creds_env": "GOOGLE_APPLICATION_CREDENTIALS" in os.environ,
        "azure_env": any(k in os.environ for k in ("AZURE_STORAGE_CONNECTION_STRING", "AZURE_STORAGE_ACCOUNT")),
        "hf_token_env_or_file": bool(os.environ.get("HF_TOKEN") or (home / ".cache/huggingface/token").is_file()),
        "restic_env": "RESTIC_REPOSITORY" in os.environ,
        "borg_env": "BORG_REPO" in os.environ,
        "mounted_remote_fs": False,
    }
    rc, mounts = _run(["findmnt", "-n", "-o", "FSTYPE"])
    remote = {"nfs", "nfs4", "cifs", "smb3", "fuse.s3fs", "ossfs", "glusterfs", "ceph"}
    candidates["mounted_remote_fs"] = any(m.strip() in remote for m in mounts.splitlines())
    # a Path is truthy whether or not it exists: evaluate existence explicitly
    detected = {k: (v.exists() if isinstance(v, Path) else bool(v))
                for k, v in candidates.items()}
    return {
        "detected": detected,
        "verdict": "NO_OFF_MACHINE_BACKUP_DESTINATION_AUTHORIZED" if not any(
            detected.values()) else "CANDIDATE_DETECTED_REQUIRES_OPERATOR_AUTHORIZATION",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--skip-network", action="store_true")
    a = ap.parse_args()
    facts = {
        "schema": "yue2-rc5-environment/1",
        "os": os_facts(),
        "cpu": cpu_facts(),
        "memory": memory_facts(),
        "gpu": gpu_facts(),
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "tools": {
            "gcc": _tool_version(["gcc", "--version"]),
            "gpp": _tool_version(["g++", "--version"]),
            "cmake": _tool_version(["cmake", "--version"]),
            "ninja": _tool_version(["ninja", "--version"]),
            "git": _tool_version(["git", "--version"]),
            "gh": _tool_version(["gh", "--version", "--"], r"gh version [\d.]+"),
            "uv": _tool_version(["uv", "--version"]),
            "ffmpeg": _tool_version(["ffmpeg", "-version"], r"ffmpeg version \S+"),
            "tmux": _tool_version(["tmux", "-V"]),
            "docker": _tool_version(["docker", "--version"]),
        },
        "storage": storage_facts(),
        "backup_capability": backup_capability_facts(),
    }
    if not a.skip_network:
        facts["network"] = network_facts()
    text = json.dumps(facts, indent=1, ensure_ascii=False) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
        print(f"wrote {a.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
