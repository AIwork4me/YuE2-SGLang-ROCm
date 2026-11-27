#!/usr/bin/env python3
"""gpu_identity.py — GPU execution identity chain & fail-loud contract.

NO SILENT FALLBACK contract: GPU work must run on the expected Radeon device.
This tool records the evidence chain and refuses to pass when identity is
unverified.

RC4.1 chain (kept): framework facts, actual placement, active execution,
worker identity, KFD visibility.

RC5 M1.4 — PHYSICAL identity binding (no "first AMD GPU" fallback). The old
sysfs fallback returned the PCI slot of the first amdgpu card it found: on a
multi-GPU host that is a guess, and a container that is given GPU #5 of 8 was
"verified" against GPU #1's address. The binding is now a closed chain::

    Framework device index
      -> HIP device properties (torch: pci_domain/bus/device ids, uuid, arch)
      -> PCI BDF (exactly one sysfs PCI function with driver amdgpu)
      -> drm render node (exactly one, and it must be exposed in /dev/dri)
      -> KFD topology node (same drm_render_minor + same PCI device id)
      -> unique id (sysfs == framework uuid, when the kernel exposes it)
      -> gfx arch
      -> compute probe (hard-bounded, isolated child)

Any ambiguity (several GPUs, same-arch peers, a device count that does not
match the exposed render nodes, a render node the container cannot see)
fails closed with GPU_DEVICE_MISMATCH.

RC5 M1.2 — PROBE HARD TIMEOUT. The compute probe runs in a separate child
process with a real wall-clock deadline. On expiry the child (ours) is
terminated, the receipt records GPU_PROGRESS_TIMEOUT with the evidence, and
the device state (VRAM back to baseline?) is checked. The old in-process
probe accepted a ``budget_s`` it never enforced, so GPU_PROGRESS_TIMEOUT was
unreachable.

Statuses (receipt field ``status``, machine-readable):
  GPU_IDENTITY_VERIFIED    device bound, arch/BDF match (probe skipped)
  GPU_EXECUTION_VERIFIED   identity bound AND compute probe passed on device
  GPU_EXECUTION_UNVERIFIED identity bound, probe explicitly skipped
  GPU_DEVICE_MISMATCH      arch/BDF != expected, or identity cannot be bound
  GPU_UNAVAILABLE          no usable device and no explicit CPU authorization
  GPU_PROGRESS_TIMEOUT     probe did not finish in the bounded budget
  GPU_EXECUTION_FAILED     probe raised / wrong result
  CPU_TEST_MODE_AUTHORIZED explicit --allow-cpu test mode (never a GPU PASS)

Exit codes: 0 verified/unverified-ok · 3 mismatch · 4 unavailable ·
5 probe failure/timeout · 2 usage error.

Usage:
  python scripts/gpu_identity.py verify --expect-arch gfx1100 \
      [--expect-bdf 0000:03:00.0] [--receipt out.json] [--skip-probe] \
      [--probe-budget-s 60]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KFD_PATH = "/dev/kfd"
STATUS_OK = {"GPU_IDENTITY_VERIFIED", "GPU_EXECUTION_VERIFIED",
             "GPU_EXECUTION_UNVERIFIED", "CPU_TEST_MODE_AUTHORIZED"}
CPU_AUTH_ENV = "YUE2_ALLOW_CPU"
CPU_AUTH_TOKEN = "1-I-AM-A-TEST"
CHILD_MODE_ENV = "YUE2_GPU_PROBE_CHILD_MODE"  # test hook: hang | fail | slow


def _load_torch():
    import torch  # lazy: CI unit tests inject a fake via sys.modules
    return torch


def kfd_visibility(dev_dri: str = "/dev/dri") -> dict:
    d = Path(dev_dri)
    render = sorted(p.name for p in d.glob("renderD*")) if d.is_dir() else []
    return {"kfd_present": Path(KFD_PATH).exists(),
            "render_nodes": render,
            "visible": Path(KFD_PATH).exists() and bool(render)}


# --------------------------------------------------------------------- BDF
def _norm_bdf(bdf: str) -> str:
    m = re.fullmatch(r"(?:0000:)?([0-9a-fA-F]{2,4}):([0-9a-fA-F]{2})\."
                     r"([0-9])", bdf.strip())
    if not m:
        return bdf.strip().lower()
    dom = m.group(1).lstrip("0") or "0"
    return f"{int(dom, 16):04x}:{int(m.group(2), 16):02x}:{m.group(3)}"


def bdf_matches(expected: str, actual: str | None) -> bool:
    if not actual or not expected:
        return False
    return _norm_bdf(expected) == _norm_bdf(actual)


def _arch_list(arch: str | None) -> list[str]:
    # gcnArchName may be "gfx1100" or "gfx1100:sramecc+:xnack-"
    if not arch:
        return []
    return [p for p in arch.split(":") if p and not p.startswith(("sramecc", "xnack"))]


def _uuid_to_hex(u) -> str | None:
    """torch uuid '6539...-...-...' / sysfs unique id 'e9d0e20bb686e6c6' ->
    lowercase hex without separators."""
    if not u or not isinstance(u, str):
        return None
    h = re.sub(r"[^0-9a-fA-F]", "", u).lower()
    return h or None


def _uuid_forms(u) -> set[str]:
    """All textual forms of a GPU unique id: the sysfs/KFD form is ASCII text
    ('e9d0e20bb686e6c6'); the torch/hip form is the same bytes packed as a
    UUID ('65396430-6532-...'). Compare through both encodings."""
    if not u or not isinstance(u, str):
        return set()
    h = re.sub(r"[^0-9a-fA-F]", "", u).lower()
    if not h:
        return set()
    out = {h, h.lower()}
    try:
        out.add(bytes.fromhex(h).decode("ascii").lower())
    except (ValueError, UnicodeDecodeError):
        pass
    out.add("".join(f"{ord(ch):02x}" for ch in h))
    return out


def uuid_consistent(a, b) -> str | bool:
    """True / False when both present and comparable, None when unknown."""
    fa, fb = _uuid_forms(a), _uuid_forms(b)
    if not fa or not fb:
        return None
    return bool(fa & fb)


# ------------------------------------------------------- physical binding
class IdentityUnbound(Exception):
    """The framework device cannot be bound to exactly one physical GPU."""


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip(), 0)
    except (OSError, ValueError):
        return None


def bind_pci_identity(torch_ns, device_index: int = 0, sys_root: str = "/sys",
                      dev_dri: str = "/dev/dri") -> dict:
    """Closed chain framework index -> physical GPU. Raises IdentityUnbound
    with a precise reason on ANY ambiguity."""
    props = torch_ns.cuda.get_device_properties(device_index)
    chain: list[str] = []
    out: dict = {"index": device_index,
                 "name": getattr(props, "name", None),
                 "arch": getattr(props, "gcnArchName", None),
                 "gcn_arch_names": _arch_list(getattr(props, "gcnArchName", None)),
                 "total_memory_bytes": getattr(props, "total_memory", None),
                 "framework_uuid": str(getattr(props, "uuid", "") or "") or None}
    chain.append(f"framework_index={device_index}")

    dom = getattr(props, "pci_domain_id", None)
    bus = getattr(props, "pci_bus_id", None)
    dev = getattr(props, "pci_device_id", None)
    if not isinstance(dom, int) or not isinstance(bus, int) or not isinstance(dev, int):
        raise IdentityUnbound("framework device properties expose no PCI ids "
                              "(pci_domain_id/pci_bus_id/pci_device_id)")
    prefix = f"{dom:04x}:{bus:02x}:{dev:02x}."
    chain.append(f"hip_pci_ids={prefix[:-1]}")

    pci_root = Path(sys_root) / "bus" / "pci" / "devices"
    if not pci_root.is_dir():
        raise IdentityUnbound(f"sysfs PCI tree missing: {pci_root}")
    # A Radeon occupies several PCI functions on one slot (03:00.0 = GPU,
    # 03:00.1 = HDMI audio, class 0x04). HIP only reports bus/device, so the
    # GPU is the ONE function whose class base is 0x03 (display controller).
    slot = sorted(p for p in pci_root.iterdir() if p.name.startswith(prefix))
    cands = [p for p in slot
             if ((_read_int(p / "class") or 0) >> 16) == 0x03]
    if not cands:
        raise IdentityUnbound(f"no display-class (0x03xxxx) PCI function "
                              f"{prefix}* under {pci_root} (slot: "
                              f"{[p.name for p in slot]})")
    if len(cands) > 1:
        raise IdentityUnbound(f"ambiguous display-class PCI functions for "
                              f"{prefix}*: {[p.name for p in cands]}")
    pci = cands[0]
    bdf = pci.name
    vendor = _read_int(pci / "vendor")
    if vendor != 0x1002:
        raise IdentityUnbound(f"{bdf}: vendor {vendor!r} is not AMD (0x1002)")
    driver_link = pci / "driver"
    try:
        driver = Path(os.readlink(driver_link)).name
    except OSError:
        driver = driver_link.name if driver_link.is_dir() else None
    if driver != "amdgpu":
        raise IdentityUnbound(f"{bdf}: driver {driver!r} != amdgpu")
    chain.append(f"pci_bdf={bdf}")
    out["pci_bdf"] = bdf

    renders = sorted(p.name for p in (pci / "drm").glob("renderD*"))
    if len(renders) != 1:
        raise IdentityUnbound(f"{bdf}: expected exactly one drm render node, "
                              f"found {renders}")
    render_node = renders[0]
    minor = int(render_node[len("renderD"):])
    exposed = kfd_visibility(dev_dri)["render_nodes"]
    if render_node not in exposed:
        raise IdentityUnbound(f"{bdf}: render node {render_node} is not exposed "
                              f"in {dev_dri} (visible: {exposed})")
    chain.append(f"render_node={render_node}")
    out["drm_render_node"] = render_node
    out["drm_render_minor"] = minor
    out["exposed_render_nodes"] = exposed

    n_dev = None
    try:
        n_dev = torch_ns.cuda.device_count()
    except Exception:  # noqa: BLE001
        n_dev = None
    out["framework_device_count"] = n_dev
    if n_dev is not None and n_dev != len(exposed):
        raise IdentityUnbound(f"ambiguous device mapping: framework sees "
                              f"{n_dev} device(s), {dev_dri} exposes "
                              f"{len(exposed)} render node(s) {exposed}")
    chain.append(f"bijective_mapping={n_dev}device(s)<->{len(exposed)}render(s)")

    kfd_node, kfd_device_id = None, None
    topo = Path(sys_root) / "class" / "kfd" / "kfd" / "topology" / "nodes"
    unreadable = 0
    if topo.is_dir():
        hits = []
        for node in topo.iterdir():
            f = node / "properties"
            if not f.is_file():
                continue
            try:
                text = f.read_text()
            except OSError:
                # nodes of GPUs outside this container are not readable; they
                # cannot be verified, so uniqueness is asserted over the
                # readable (i.e. accessible) nodes and the count is disclosed
                unreadable += 1
                continue
            kv = {}
            for line in text.splitlines():
                if " " in line:
                    k, _, v = line.partition(" ")
                    kv[k.strip()] = v.strip()
            if kv.get("drm_render_minor") == str(minor):
                hits.append((node.name, kv))
        if len(hits) != 1:
            raise IdentityUnbound(f"KFD topology: {len(hits)} accessible node(s) "
                                  f"own render minor {minor}")
        kfd_node, kv = hits[0]
        kfd_device_id = int(kv["device_id"]) if kv.get("device_id", "").isdigit() else None
        pci_dev = _read_int(pci / "device")
        if kfd_device_id is not None and pci_dev is not None \
                and kfd_device_id != pci_dev:
            raise IdentityUnbound(f"KFD node {kfd_node} device_id "
                                  f"{kfd_device_id:#x} != PCI {pci_dev:#x}")
        chain.append(f"kfd_node={kfd_node}")
    out["kfd_node"] = kfd_node
    out["kfd_topology_available"] = topo.is_dir()
    out["kfd_nodes_unreadable"] = unreadable

    cards = sorted(p.name for p in (pci / "drm").glob("card[0-9]*"))
    unique_id = None
    if len(cards) == 1:
        out["drm_card"] = cards[0]
        uf = Path(sys_root) / "class" / "drm" / cards[0] / "device" / "unique_id"
        try:
            unique_id = uf.read_text().strip() or None
        except OSError:
            unique_id = None
    out["sysfs_unique_id"] = unique_id
    cons = uuid_consistent(out["framework_uuid"], unique_id)
    out["uuid_consistent"] = cons
    if cons is False:
        raise IdentityUnbound(f"unique id mismatch: framework "
                              f"{out['framework_uuid']} != sysfs {unique_id}")
    if cons:
        chain.append("unique_id=sysfs==framework")
    out["binding_chain"] = chain
    return out


# ------------------------------------------------------------------- probe
def _sdpa_check(torch_ns) -> dict:
    """SDPA: optimized path vs math reference on a small causal case."""
    import torch.nn.functional as F  # noqa: N812
    from torch.nn.attention import SDPBackend, sdpa_kernel
    g = torch_ns.Generator(device="cpu").manual_seed(1234)
    q = torch_ns.randn(1, 4, 256, 64, generator=g).to("cuda", torch_ns.bfloat16)
    k = torch_ns.randn(1, 4, 256, 64, generator=g).to("cuda", torch_ns.bfloat16)
    v = torch_ns.randn(1, 4, 256, 64, generator=g).to("cuda", torch_ns.bfloat16)
    with sdpa_kernel(SDPBackend.MATH):
        ref = F.scaled_dot_product_attention(q, k, v, is_causal=True)
    res = {"reference_backend": "MATH"}
    best = None
    for be in (SDPBackend.FLASH_ATTENTION, SDPBackend.EFFICIENT_ATTENTION):
        try:
            with sdpa_kernel(be):
                o = F.scaled_dot_product_attention(q, k, v, is_causal=True)
            torch_ns.cuda.synchronize()
            if not bool(torch_ns.isfinite(o).all()):
                res[be.name] = "NON_FINITE"
                continue
            d = float((o.float() - ref.float()).abs().max().item())
            res[be.name] = {"max_abs_diff_vs_math": round(d, 6), "finite": True}
            best = d if best is None else min(best, d)
        except Exception as e:  # noqa: BLE001 - reported, not hidden
            res[be.name] = f"UNAVAILABLE: {type(e).__name__}"
    if best is None:
        raise RuntimeError(f"no optimized SDPA backend produced finite output: {res}")
    if best > 0.05:
        raise RuntimeError(f"SDPA disagrees with the math reference: {res}")
    res["best_max_abs_diff"] = round(best, 6)
    res["has_aten_flash_attention_forward"] = hasattr(
        torch_ns.ops.aten, "_flash_attention_forward")
    return res


def probe_compute(torch_ns, device_index: int = 0, full: bool = True) -> dict:
    """The verified compute itself (runs INSIDE the probe child). ``full=False``
    keeps only the fp32 matmul entry check — used for injected fake torch
    namespaces in unit tests, which cannot exercise SDPA/bf16."""
    t0 = time.monotonic()
    dev = torch_ns.device(f"cuda:{device_index}")
    a = torch_ns.randn(256, 256, device=dev, dtype=torch_ns.float32)
    b = torch_ns.randn(256, 256, device=dev, dtype=torch_ns.float32)
    c = a @ b
    torch_ns.cuda.synchronize(device_index)
    checksum = float(c.sum().item())
    # independent CPU recompute of one entry for correctness evidence
    i, j = 7, 13
    recompute = float((a[i].to("cpu") * b[:, j].to("cpu")).sum().item())
    got = float(c[i, j].item())
    if not math.isclose(got, recompute, rel_tol=1e-3, abs_tol=1e-3):
        raise RuntimeError(
            f"GPU probe result mismatch: device={got} cpu_recompute={recompute}")
    facts = {
        "probe": "matmul256-fp32+bf16+sdpa" if full else "matmul256-fp32",
        "probe_device": str(c.device),
        "probe_checksum": round(checksum, 3),
        "probe_entry_cpu_recompute": round(recompute, 6),
        "probe_entry_device": round(got, 6),
    }
    if not full:
        facts["probe_wall_s"] = round(time.monotonic() - t0, 3)
        return facts
    g = torch_ns.Generator(device="cpu").manual_seed(20261124)
    x = torch_ns.randn(1024, 1024, generator=g).to("cuda", torch_ns.bfloat16)
    y = torch_ns.randn(1024, 1024, generator=g).to("cuda", torch_ns.bfloat16)
    z = (x @ y).float()
    torch_ns.cuda.synchronize(device_index)
    if not bool(torch_ns.isfinite(z).all()):
        raise RuntimeError("bf16 matmul produced non-finite values")
    ref = x[:64].float() @ y[:, :64].float()
    err = float((z[:64, :64] - ref).abs().max().item())
    scale = float(ref.abs().max().item()) or 1.0
    if err / scale > 0.05:
        raise RuntimeError(f"bf16 matmul far from its fp32 reference: {err}")
    facts["bf16_matmul_1024_max_rel_err"] = round(err / scale, 6)
    facts["sdpa"] = _sdpa_check(torch_ns)
    facts["probe_wall_s"] = round(time.monotonic() - t0, 3)
    return facts


def probe_device(torch_ns, device_index: int = 0):
    """In-process fp32 probe — ONLY for injected (fake) torch namespaces in
    unit tests (no hard timeout is possible in-process); a real runtime
    always goes through probe_isolated(). The unenforced ``budget_s``
    parameter of the RC4.1 signature is gone on purpose."""
    return probe_compute(torch_ns, device_index, full=False)


class ProbeTimeout(TimeoutError):
    def __init__(self, message, evidence: dict):
        super().__init__(message)
        self.evidence = evidence


def _read_vram_used(card: str | None, sys_root: str = "/sys") -> int | None:
    if not card:
        return None
    try:
        return int((Path(sys_root) / "class/drm" / card / "device"
                    / "mem_info_vram_used").read_text().strip())
    except (OSError, ValueError):
        return None


def _stop_own_child(child: subprocess.Popen) -> str:
    """Terminate a probe child WE spawned (never anything else)."""
    if child.poll() is not None:
        return "already_exited"
    child.send_signal(signal.SIGTERM)
    try:
        child.wait(timeout=5)
        return "terminated_by_sigterm"
    except subprocess.TimeoutExpired:
        pass
    child.kill()  # SIGKILL — our own child, device may be hung
    try:
        child.wait(timeout=10)
        return "killed_by_sigkill"
    except subprocess.TimeoutExpired:
        return "UNINTERRUPTIBLE"


def probe_isolated(device_index: int = 0, budget_s: float = 60.0,
                   card: str | None = None, sys_root: str = "/sys") -> dict:
    """Run the compute probe in a separate process under a real wall-clock
    deadline. Raises ProbeTimeout (a TimeoutError) when the budget expires."""
    t0 = time.monotonic()
    vram_before = _read_vram_used(card, sys_root)
    fd, result_path = tempfile.mkstemp(prefix="yue2_gpu_probe_", suffix=".json")
    os.close(fd)
    try:
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "__probe__",
             "--device-index", str(device_index), "--result", result_path],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
    except OSError as e:
        raise RuntimeError(f"cannot spawn probe child: {e}") from e
    try:
        try:
            out_s, err_s = child.communicate(timeout=budget_s)
        except subprocess.TimeoutExpired:
            how = _stop_own_child(child)
            try:
                out_s, err_s = child.communicate(timeout=5)
            except (subprocess.TimeoutExpired, OSError, ValueError):
                out_s, err_s = "", ""
            vram_after = _read_vram_used(card, sys_root)
            state = "UNKNOWN"
            if vram_before is not None and vram_after is not None:
                deadline = time.monotonic() + 10
                while vram_after > vram_before + 64 * 2**20 \
                        and time.monotonic() < deadline:
                    time.sleep(1)
                    vram_after = _read_vram_used(card, sys_root)
                state = ("VRAM_RELEASED" if vram_after <= vram_before + 64 * 2**20
                         else "VRAM_NOT_RELEASED")
            raise ProbeTimeout(
                f"probe exceeded {budget_s}s wall-clock (child {child.pid})",
                {"child_pid": child.pid, "child_end_state": how,
                 "child_reaped": child.poll() is not None,
                 "elapsed_s": round(time.monotonic() - t0, 3),
                 "budget_s": budget_s,
                 "vram_before_bytes": vram_before,
                 "vram_after_bytes": vram_after,
                 "gpu_state_after_timeout": state,
                 "stderr_tail": (err_s or "")[-1500:]}) from None
        if child.returncode != 0:
            raise RuntimeError(
                f"probe child rc={child.returncode}: {(err_s or out_s)[-1500:]}")
        try:
            facts = json.loads(Path(result_path).read_text())
        except (OSError, ValueError) as e:
            raise RuntimeError(f"probe child wrote no result: {e}") from e
    finally:
        try:
            os.unlink(result_path)
        except OSError:
            pass
    facts["probe_mode"] = "isolated_subprocess"
    facts["probe_child_pid"] = child.pid
    facts["probe_budget_s"] = budget_s
    facts["probe_total_wall_s"] = round(time.monotonic() - t0, 3)
    return facts


def _probe_child_main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gpu_identity.py __probe__")
    ap.add_argument("--device-index", type=int, default=0)
    ap.add_argument("--result", required=True)
    a = ap.parse_args(argv)
    mode = os.environ.get(CHILD_MODE_ENV, "")
    if mode == "hang":  # test hook: simulate a hung device (self-limiting)
        time.sleep(45)
    try:
        if mode == "fail":  # test hook
            raise RuntimeError("injected probe failure")
        facts = probe_compute(_load_torch(), a.device_index)
        Path(a.result).write_text(json.dumps(facts))
        return 0
    except BaseException as e:  # noqa: BLE001 - evidence for the parent
        print(f"probe child failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


# ------------------------------------------------------------------ verify
def _self_starttime() -> str | None:
    try:
        data = Path(f"/proc/{os.getpid()}/stat").read_text()
        return data[data.rindex(")") + 1:].split()[19]
    except (OSError, ValueError):
        return None


def _self_cmdline() -> str:
    try:
        return Path(f"/proc/{os.getpid()}/cmdline").read_bytes().replace(
            b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        return ""


def verify(expected_arch: str | None = "gfx1100", expected_bdf: str | None = None,
           run_probe: bool = True, cpu_authorized: bool = False,
           receipt_path: Path | None = None, torch_ns=None, device_index: int = 0,
           probe_budget_s: float = 60.0, sys_root: str = "/sys",
           dev_dri: str = "/dev/dri") -> dict:
    """Build the identity receipt. Returns dict with `status` and `ok`."""
    injected = torch_ns is not None
    who = {"pid": os.getpid(), "starttime": _self_starttime(),
           "cmdline": _self_cmdline()}
    receipt = {
        "receipt_type": "gpu_identity",
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "expected": {"arch": expected_arch, "bdf": expected_bdf,
                     "cpu_authorized": cpu_authorized},
        "worker": who,
        "kfd": kfd_visibility(dev_dri),
    }
    try:
        torch = torch_ns if torch_ns is not None else _load_torch()
        receipt["framework"] = {
            "torch_version": getattr(torch, "__version__", "unknown"),
            "hip_version": str(getattr(torch.version, "hip", None)),
            "cuda_version": str(getattr(torch.version, "cuda", None)),
            "cuda_api_available": bool(torch.cuda.is_available()),
        }
    except Exception as e:  # import failure / broken runtime
        receipt["framework"] = {"error": f"{type(e).__name__}: {e}"}
        if cpu_authorized:
            receipt["status"] = "CPU_TEST_MODE_AUTHORIZED"
            receipt["reason"] = (f"torch runtime unusable ({e}); CPU mode "
                                 "explicitly authorized (test-only, never "
                                 "a GPU PASS)")
            receipt["ok"] = True
        else:
            receipt["status"] = "GPU_UNAVAILABLE"
            receipt["reason"] = f"torch runtime unusable: {e}"
            receipt["ok"] = False
        return _finish(receipt, receipt_path)

    fw = receipt["framework"]
    if fw.get("cuda_version", "None") not in ("None", None):
        receipt["status"] = "GPU_DEVICE_MISMATCH"
        receipt["reason"] = ("CUDA-only torch build (torch.version.cuda set); "
                             "this project requires the ROCm/HIP stack")
        receipt["ok"] = False
        return _finish(receipt, receipt_path)

    if not fw["cuda_api_available"]:
        if cpu_authorized:
            receipt["status"] = "CPU_TEST_MODE_AUTHORIZED"
            receipt["reason"] = ("no GPU visible; CPU mode explicitly "
                                 "authorized (test-only, never a GPU PASS)")
            receipt["ok"] = True
        else:
            receipt["status"] = "GPU_UNAVAILABLE"
            receipt["reason"] = ("torch.cuda.is_available()=False and no "
                                 "explicit CPU authorization (GPU_REQUIRED "
                                 "default; NO silent CPU fallback)")
            receipt["ok"] = False
        return _finish(receipt, receipt_path)

    try:
        props = torch.cuda.get_device_properties(device_index)
        arch = getattr(props, "gcnArchName", None)
        name = getattr(props, "name", None)
        total = getattr(props, "total_memory", None)
    except Exception as e:
        receipt["status"] = "GPU_UNAVAILABLE"
        receipt["reason"] = f"get_device_properties failed: {e}"
        receipt["ok"] = False
        return _finish(receipt, receipt_path)

    receipt["device"] = {"index": device_index, "name": name, "arch": arch,
                         "gcn_arch_names": _arch_list(arch),
                         "total_memory_bytes": total,
                         "total_memory_gib": (round(total / 2**30, 2)
                                              if isinstance(total, int) else None)}
    if expected_arch and expected_arch not in _arch_list(arch):
        receipt["status"] = "GPU_DEVICE_MISMATCH"
        receipt["reason"] = (f"device arch {arch!r} does not include expected "
                             f"{expected_arch!r}")
        receipt["ok"] = False
        return _finish(receipt, receipt_path)

    # ---- physical binding (M1.4): never guess ------------------------------
    try:
        bound = bind_pci_identity(torch, device_index, sys_root=sys_root,
                                  dev_dri=dev_dri)
    except IdentityUnbound as e:
        receipt["status"] = "GPU_DEVICE_MISMATCH"
        receipt["reason"] = (f"physical GPU identity could not be bound "
                             f"(AMBIGUOUS/UNVERIFIABLE, fail-closed): {e}")
        receipt["ok"] = False
        receipt["device"]["pci_bdf"] = None
        return _finish(receipt, receipt_path)
    device = receipt["device"]
    device.update(bound)
    bdf = bound["pci_bdf"]
    if expected_bdf and not bdf_matches(expected_bdf, bdf):
        receipt["status"] = "GPU_DEVICE_MISMATCH"
        receipt["reason"] = (f"device PCI BDF {bdf!r} != expected "
                             f"{expected_bdf!r}")
        receipt["ok"] = False
        return _finish(receipt, receipt_path)
    receipt["bound_bdf"] = bdf

    receipt["status"] = "GPU_IDENTITY_VERIFIED"
    if not run_probe:
        receipt["status"] = "GPU_EXECUTION_UNVERIFIED"
        receipt["ok"] = True
        return _finish(receipt, receipt_path)

    try:
        if injected:
            facts = probe_compute(torch, device_index=device_index, full=False)
            facts["probe_mode"] = ("in-process(injected torch namespace; "
                                   "unit-test only)")
        else:
            facts = probe_isolated(device_index, budget_s=probe_budget_s,
                                   card=bound.get("drm_card"), sys_root=sys_root)
        receipt["probe_facts"] = facts
        receipt["status"] = "GPU_EXECUTION_VERIFIED"
        receipt["ok"] = True
    except TimeoutError as e:
        receipt["status"] = "GPU_PROGRESS_TIMEOUT"
        receipt["reason"] = f"probe exceeded {probe_budget_s}s: {e}"
        receipt["probe_timeout_evidence"] = getattr(e, "evidence", {})
        ev = receipt["probe_timeout_evidence"]
        if ev.get("child_end_state") == "UNINTERRUPTIBLE" \
                or ev.get("gpu_state_after_timeout") == "VRAM_NOT_RELEASED":
            receipt["device_state"] = "BLOCKED"
            receipt["reason"] += (" — device did not recover (uninterruptible " +
                                  "child or VRAM not released): treat as BLOCKED")
        receipt["ok"] = False
    except Exception as e:
        receipt["status"] = "GPU_EXECUTION_FAILED"
        receipt["reason"] = f"probe failed: {type(e).__name__}: {e}"
        receipt["ok"] = False
    return _finish(receipt, receipt_path)


def _finish(receipt: dict, receipt_path: Path | None) -> dict:
    receipt["verdict"] = "PASS" if receipt.get("ok") else "FAIL"
    if receipt_path:
        p = Path(receipt_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".tmp.{os.getpid()}")
        with open(tmp, "w") as f:
            f.write(json.dumps(receipt, indent=1) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    return receipt


EXIT_BY_STATUS = {"GPU_DEVICE_MISMATCH": 3, "GPU_UNAVAILABLE": 4,
                  "GPU_PROGRESS_TIMEOUT": 5, "GPU_EXECUTION_FAILED": 5}


def main(argv=None) -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "__probe__":
        return _probe_child_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("verify", "probe"):
        s = sub.add_parser(name)
        s.add_argument("--expect-arch", default=os.environ.get(
            "YUE2_EXPECT_GPU_ARCH", "gfx1100"),
            help="required gcnArchName (default gfx1100; empty string skips)")
        s.add_argument("--expect-bdf", default=os.environ.get(
            "YUE2_EXPECT_GPU_BDF"), help="exact PCI BDF (optional when exactly "
            "one GPU is visible; mandatory to disambiguate several)")
        s.add_argument("--receipt", type=Path, default=None)
        s.add_argument("--device-index", type=int, default=0)
        s.add_argument("--probe-budget-s", type=float, default=60.0,
                       help="hard wall-clock deadline for the isolated probe")
        s.add_argument("--sys-root", default="/sys",
                       help="sysfs root (test injection only)")
        s.add_argument("--dev-dri", default="/dev/dri",
                       help="render node dir (test injection only)")
        if name == "verify":
            s.add_argument("--skip-probe", action="store_true")
            s.add_argument("--allow-cpu", action="store_true",
                           help="explicit CPU test-mode authorization "
                                "(never reported as GPU PASS)")
    a = ap.parse_args(argv)
    cpu_auth = bool(getattr(a, "allow_cpu", False) or
                    os.environ.get(CPU_AUTH_ENV) == CPU_AUTH_TOKEN)
    r = verify(expected_arch=a.expect_arch or None, expected_bdf=a.expect_bdf,
               run_probe=(a.cmd == "probe" or not getattr(a, "skip_probe", False)),
               cpu_authorized=cpu_auth, receipt_path=a.receipt,
               device_index=a.device_index, probe_budget_s=a.probe_budget_s,
               sys_root=a.sys_root, dev_dri=a.dev_dri)
    print(json.dumps(r, indent=1))
    return EXIT_BY_STATUS.get(r["status"], 0 if r["ok"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
