#!/usr/bin/env python3
"""check_environment.py - portable ROCm/YuE2 environment diagnostic.

Captures OS, CPU, GPU (PCI + rocminfo + rocm-smi/amd-smi), device permissions,
memory, disk, Python, network reachability, gh auth, ROCm versions, and
(optional, if installed) the torch stack. Emits human-readable log and
machine-readable JSON. Works on any Linux ROCm host (gfx1151, gfx1100, ...).

Usage:
  python check_environment.py [--json OUT.json] [--check-torch]
Exit 0 if no blocking issue found, 1 otherwise.
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
import urllib.request
from pathlib import Path

BLOCKERS: list[str] = []
WARNINGS: list[str] = []


def run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def section(title):
    print(f"\n=== {title} ===")


def capture_os(env):
    section("Operating system")
    code, out, _ = run(["cat", "/etc/os-release"])
    print(out)
    env["os"] = dict(re.findall(r'^(\w+)=(.*)$', out, re.M))
    env["kernel"] = platform.release()
    print("kernel:", env["kernel"])


def capture_cpu(env):
    section("CPU")
    code, out, _ = run(["lscpu"])
    keep = [l for l in out.splitlines() if re.match(
        r"(Model name|Architecture|CPU\(s\)|Socket|NUMA|Thread)", l)]
    print("\n".join(keep))
    env["cpu"] = {k: v.strip() for k, v in
                  (l.split(":", 1) for l in keep if ":" in l)}


def capture_gpu(env):
    section("GPU")
    code, out, _ = run(["lspci", "-nn"])
    gpus = [l for l in out.splitlines() if re.search(r"VGA|Display|1002:744", l)]
    print("\n".join(gpus) if gpus else "lspci: no output")
    env["pci_vga"] = gpus

    env["rocm"] = {}
    code, out, _ = run(["rocminfo"])
    agents = re.findall(r"Name:\s+(\S+)\s*\n\s*Uuid:\s+(\S+)", out) if code == 0 else []
    gfx = re.findall(r"amdgcn-amd-amdhsa--(\S+)", out)
    env["rocm"]["rocminfo_present"] = code == 0
    env["rocm"]["agents"] = [a[0] for a in agents]
    env["rocm"]["gfx_targets"] = sorted(set(gfx))
    m = re.search(r"ROCk module version (\S+)", out)
    env["rocm"]["rock_module"] = m.group(1) if m else None
    print("gfx targets:", env["rocm"]["gfx_targets"])

    for tool in ("rocm-smi", "amd-smi"):
        code, out, err = run([tool])
        env["rocm"][tool] = {"present": code != 127, "rc": code,
                             "summary": (out or err).splitlines()[:12]}
        print(f"{tool}: rc={code}")

    ver = Path("/opt/rocm/.info/version")
    env["rocm"]["host_userspace_version"] = ver.read_text().strip() if ver.is_file() else None
    print("host ROCm userspace:", env["rocm"]["host_userspace_version"])

    if not gfx:
        BLOCKERS.append("no amdgcn compute target visible in rocminfo")
    if code == 0 and "gfx1100" not in gfx:
        WARNINGS.append(f"gfx1100 not among visible targets: {gfx}")


def capture_devices(env):
    section("Device nodes and permissions")
    kfd = Path("/dev/kfd")
    dri = sorted(Path("/dev/dri").glob("renderD*")) if Path("/dev/dri").is_dir() else []
    env["devices"] = {
        "kfd": {"exists": kfd.exists(),
                "mode": oct(kfd.stat().st_mode & 0o777) if kfd.exists() else None,
                "uid": kfd.stat().st_uid if kfd.exists() else None,
                "gid": kfd.stat().st_gid if kfd.exists() else None},
        "render_nodes": [str(d) for d in dri],
    }
    print(json.dumps(env["devices"]))
    if not kfd.exists():
        BLOCKERS.append("/dev/kfd missing: no compute access")
    if not dri:
        BLOCKERS.append("no /dev/dri/renderD* nodes")


def capture_mem_disk(env):
    section("Memory and disk")
    code, out, _ = run(["free", "-h"])
    print(out)
    for line in out.splitlines():
        if line.startswith("Mem:"):
            env["memory_total_human"] = line.split()[1]
    code, out, _ = run(["df", "-h", "/"])
    print(out)
    env["disk_root"] = out.splitlines()[-1]
    ino = run(["df", "-i", "/workspace" if Path("/workspace").is_dir() else "/"])[1]
    env["inodes"] = ino.splitlines()[-1] if ino else None


def capture_python(env):
    section("Python and tools")
    env["python"] = sys.version.split()[0]
    for tool in ("git", "git-lfs", "ffmpeg", "jq", "gh", "gcc", "cmake", "ninja"):
        p = shutil.which(tool)
        env["tools"] = env.get("tools", {})
        env["tools"][tool] = p
        print(f"{tool}: {p or 'MISSING'}")
        if tool in ("git", "ffmpeg") and not p:
            BLOCKERS.append(f"required tool missing: {tool}")


def capture_network(env):
    section("Network reachability")
    targets = ["https://github.com", "https://api.github.com", "https://huggingface.co",
               "https://repo.amd.com", "https://pypi.org", "https://hf-mirror.com",
               "https://codeload.github.com"]
    env["network"] = {}
    for u in targets:
        attempts = []
        status = None
        for _ in range(3):  # egress proxy is intermittently flaky per-connection
            try:
                req = urllib.request.Request(u, method="GET",
                                             headers={"Range": "bytes=0-0"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    status = r.status
                    attempts.append(r.status)
                    break
            except Exception as e:
                attempts.append(f"FAIL: {type(e).__name__}")
        env["network"][u] = {"status": status, "attempts": attempts}
        print(f"{u} -> {status} (attempts: {attempts})")
    ok = lambda u: env["network"][u]["status"] == 206 or env["network"][u]["status"] == 200  # noqa: E731
    if not ok("https://repo.amd.com"):
        BLOCKERS.append("repo.amd.com unreachable: cannot install required wheels")
    if not ok("https://huggingface.co") and not ok("https://hf-mirror.com"):
        BLOCKERS.append("neither huggingface.co nor hf-mirror.com reachable")


def capture_gh(env):
    section("GitHub CLI")
    code, out, err = run(["gh", "auth", "status"])
    print((out or err))
    env["gh_auth"] = {"rc": code, "out": (out or err)[:400]}
    code, out, _ = run(["gh", "api", "user", "--jq", ".login"])
    env["gh_user"] = out if code == 0 else None
    print("authenticated as:", env["gh_user"])
    code, out, _ = run(["gh", "api", "repos/AIwork4me/YuE2-SGLang-ROCm",
                        "--jq", ".full_name + \" visibility=\" + .visibility"])
    env["gh_evidence_repo"] = out if code == 0 else f"FAIL({code})"
    print("evidence repo:", env["gh_evidence_repo"])


def capture_torch(env):
    section("PyTorch")
    try:
        import torch  # noqa
    except Exception as e:
        env["torch"] = {"installed": False, "error": str(e)[:200]}
        print("torch not importable:", e)
        return
    import torchvision, torchaudio  # noqa
    t = {"installed": True, "torch": torch.__version__,
         "torchvision": torchvision.__version__, "torchaudio": torchaudio.__version__,
         "hip": torch.version.hip, "cuda": torch.version.cuda}
    if torch.cuda.is_available():
        t["gpu_name"] = torch.cuda.get_device_name(0)
        props = torch.cuda.get_device_properties(0)
        t["gcnArchName"] = getattr(props, "gcnArchName", None)
        t["total_memory_GiB"] = round(props.total_memory / 2**30, 1)
        try:
            a = torch.randn(512, 512, device="cuda", dtype=torch.bfloat16)
            c = a @ a
            torch.cuda.synchronize()
            t["bf16_gemm"] = bool(torch.isfinite(c).all())
        except Exception as e:
            t["bf16_gemm"] = f"FAIL: {e}"[:200]
    env["torch"] = t
    print(json.dumps(t, indent=1))
    if t.get("bf16_gemm") is not True:
        BLOCKERS.append("torch GPU compute not verified")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--check-torch", action="store_true")
    args = ap.parse_args()
    env = {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "host": os.uname().nodename, "user": os.environ.get("USER") or "root",
           "uid": os.getuid(), "groups": run(["id", "-nG"])[1]}
    capture_os(env)
    capture_cpu(env)
    capture_gpu(env)
    capture_devices(env)
    capture_mem_disk(env)
    capture_python(env)
    capture_network(env)
    capture_gh(env)
    if args.check_torch:
        capture_torch(env)
    env["blockers"] = BLOCKERS
    env["warnings"] = WARNINGS
    section("Verdict")
    print("BLOCKERS:", BLOCKERS or "none")
    print("WARNINGS:", WARNINGS or "none")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(env, indent=1, sort_keys=True) + "\n")
        print(f"\nJSON written to {args.json}")
    return 1 if BLOCKERS else 0


if __name__ == "__main__":
    raise SystemExit(main())
