"""gpu_identity.py unit tests (RC4.1 M1.4 matrix → RC5 M1.2 + M1.4).

Covers the fail-loud contract states with a fake torch namespace and a fake
sysfs PCI/drm/KFD tree (no GPU, no torch import required):

  * RC5 M1.4 physical identity binding: framework index -> HIP PCI ids ->
    PCI BDF -> drm render node -> KFD node -> unique id. Multi-GPU and
    same-arch hosts, containers given GPU #5 of 8, slots with two PCI
    functions and device-count mismatches all fail closed. The RC4.1
    fallback ("first amdgpu card in /sys/class/drm") must not exist.
  * RC5 M1.2 probe hard timeout: a REAL hung probe child is terminated at a
    real wall-clock deadline and reported GPU_PROGRESS_TIMEOUT.

Real-W7900 verification is a separate hardware gate
(reports/w7900_rc5/00_ENVIRONMENT.json, 01_P0_P1_CLOSURE.json).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "gpu_identity_mod", REPO / "scripts" / "gpu_identity.py")
gi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gi)


class FakeTensor:
    def __init__(self, device, value=1.0):
        self.device = device
        self.value = value

    def sum(self):
        t = types.SimpleNamespace()
        t.item = lambda: self.value
        return t

    def item(self):
        return self.value

    def to(self, dev):
        return self

    def __getitem__(self, idx):
        return FakeTensor(self.device, self.value)

    def __mul__(self, other):
        return FakeTensor(self.device, self.value * other.value)


class FakeMatmulTensor(FakeTensor):
    def __matmul__(self, other):
        return FakeMatmulTensor(self.device, self.value * other.value)

    def __mul__(self, other):
        return self


def _ascii_uuid(text: str) -> str:
    """torch/hip form of a sysfs unique id ('e9d0...' ASCII -> packed UUID)."""
    h = text.encode().hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


GPU5 = {"dom": 0, "bus": 0x23, "dev": 0, "fn": 0, "device_id": 0x744B,
        "minor": 129, "unique": "7e99b4d2506e050a", "kfd_node": "3"}


def fake_torch(available=True, arch="gfx1100", name="AMD Radeon PRO W7900D",
               hip="7.14.60850", cuda_ns=None, version="2.12.0+rocm7.14.1",
               total_memory=51_522_830_336, gpu=GPU5, pci_ids=True,
               device_count=1, uuid=None):
    ns = types.SimpleNamespace()
    ns.__version__ = version
    ns.version = types.SimpleNamespace(hip=hip, cuda=cuda_ns)
    ns.cuda = types.SimpleNamespace()
    ns.cuda.is_available = lambda: available
    ns.cuda.device_count = lambda: device_count
    if available:
        extra = {}
        if pci_ids:
            extra = {"pci_domain_id": gpu["dom"], "pci_bus_id": gpu["bus"],
                     "pci_device_id": gpu["dev"],
                     "uuid": uuid if uuid is not None else _ascii_uuid(gpu["unique"])}
        props = types.SimpleNamespace(gcnArchName=arch, name=name,
                                      total_memory=total_memory, **extra)
        ns.cuda.get_device_properties = lambda i: props
    ns.device = lambda s: types.SimpleNamespace(_s=s)
    ns.randn = lambda *a, device=None, dtype=None: FakeMatmulTensor(
        f"{device._s}")
    ns.float32 = "fp32"
    ns.cuda.synchronize = lambda i: None
    return ns


def write_gpu_sysfs(root: Path, g: dict, exposed: list[str] | None = None,
                    kfd: bool = True, fn_audio: bool = False,
    kfd_device_id: int | None = None, unique: str | None = ""):
    """One GPU in a fake sysfs: PCI function(s), drm nodes, KFD topology."""
    bdf = f"{g['dom']:04x}:{g['bus']:02x}:{g['dev']:02x}.0"
    pci = root / "sys/bus/pci/devices" / bdf
    (pci / "drm").mkdir(parents=True)
    (pci / "class").write_text("0x030000\n")
    (pci / "vendor").write_text("0x1002\n")
    (pci / "device").write_text(f"0x{g['device_id']:x}\n")
    os.symlink("../../../bus/pci/drivers/amdgpu", pci / "driver")
    render = f"renderD{g['minor']}"
    card = f"card{g.get('card', g['bus'])}"
    (pci / "drm" / render).write_text("")
    (pci / "drm" / card).write_text("")
    if fn_audio:
        aud = root / "sys/bus/pci/devices" / bdf.replace(".0", ".1")
        aud.mkdir(parents=True)
        (aud / "class").write_text("0x040300\n")
        (aud / "vendor").write_text("0x1002\n")
    dev_dir = root / "sys/class/drm" / card / "device"
    dev_dir.mkdir(parents=True)
    if unique is not None:
        (dev_dir / "unique_id").write_text(unique or g["unique"] + "\n")
    if exposed and render in exposed:
        (root / "dev/dri").mkdir(parents=True, exist_ok=True)
        (root / "dev/dri" / render).write_text("")
    if kfd:
        node = root / "sys/class/kfd/kfd/topology/nodes" / g["kfd_node"]
        node.mkdir(parents=True)
        did = g["device_id"] if kfd_device_id is None else kfd_device_id
        (node / "properties").write_text(
            f"agent2\nvendor_id 4098\ndevice_id {did}\n"
            f"location PCIe\nsimd_count 192\ndrm_render_minor {g['minor']}\n")


def single(tmp_path, **kw):
    root = tmp_path / "fs"
    gpu = kw.pop("gpu", GPU5)
    write_gpu_sysfs(root, gpu, exposed=[f"renderD{gpu['minor']}"], **kw)
    return root, str(root / "sys"), str(root / "dev/dri")


# ------------------------------------------------------------ RC4.1 contract
def test_happy_path_execution_verified(tmp_path):
    _root, sysr, dri = single(tmp_path, fn_audio=True)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(),
                  receipt_path=tmp_path / "r.json", sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_VERIFIED"
    assert r["ok"] is True
    assert r["device"]["total_memory_gib"] == 47.98
    assert r["bound_bdf"] == "0000:23:00.0"
    assert r["device"]["pci_bdf"] == "0000:23:00.0"
    chain = r["device"]["binding_chain"]
    assert any(c.startswith("kfd_node=") for c in chain)
    assert any(c.startswith("unique_id=") for c in chain)
    assert r["device"]["uuid_consistent"] is True
    written = json.loads((tmp_path / "r.json").read_text())
    assert written["status"] == "GPU_EXECUTION_VERIFIED"
    assert written["worker"]["pid"] > 0
    assert written["framework"]["hip_version"] == "7.14.60850"


def test_arch_mismatch_fails_loud(tmp_path):
    _root, sysr, dri = single(tmp_path)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(arch="gfx1151"),
                  sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert r["ok"] is False
    assert "gfx1151" in r["reason"]


def test_cuda_only_build_rejected(tmp_path):
    _root, sysr, dri = single(tmp_path)
    r = gi.verify(expected_arch="gfx1100",
                  torch_ns=fake_torch(cuda_ns="12.4"), sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert "ROCm/HIP" in r["reason"]


def test_gpu_unavailable_without_cpu_auth(tmp_path):
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(available=False))
    assert r["status"] == "GPU_UNAVAILABLE"
    assert r["ok"] is False
    assert "NO silent CPU fallback" in r["reason"]


def test_cpu_authorized_is_test_mode_not_gpu_pass(tmp_path):
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(available=False),
                  cpu_authorized=True)
    assert r["status"] == "CPU_TEST_MODE_AUTHORIZED"
    assert r["ok"] is True
    assert "never a GPU PASS" in r["reason"]


def test_wrong_bdf_mismatch(tmp_path):
    """A BDF that is not the bound device is a hard mismatch (RC4.1 accepted
    'identity verified' here when the fallback found nothing)."""
    _root, sysr, dri = single(tmp_path)
    r = gi.verify(expected_arch="gfx1100", expected_bdf="0000:ff:00.0",
                  torch_ns=fake_torch(), run_probe=False, sys_root=sysr,
                  dev_dri=dri)
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert r["ok"] is False
    assert "PCI BDF" in r["reason"]


def test_matching_bdf_passes(tmp_path):
    _root, sysr, dri = single(tmp_path)
    r = gi.verify(expected_arch="gfx1100", expected_bdf="23:00.0",
                  torch_ns=fake_torch(), run_probe=False, sys_root=sysr,
                  dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED"
    assert r["ok"] is True


def test_identity_verified_without_probe(tmp_path):
    _root, sysr, dri = single(tmp_path)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(),
                  run_probe=False, sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED"


def test_probe_failure_is_execution_failed(tmp_path):
    _root, sysr, dri = single(tmp_path)
    ns = fake_torch()

    def boom(*a, **k):
        raise RuntimeError("HIP error: device lost (test)")
    ns.randn = boom
    r = gi.verify(expected_arch="gfx1100", torch_ns=ns, sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_FAILED"
    assert "device lost" in r["reason"]
    assert r["ok"] is False


def test_torch_import_failure_is_unavailable(tmp_path, monkeypatch):
    def boom():
        raise ImportError("No module named torch (test)")
    monkeypatch.setattr(gi, "_load_torch", boom)
    r = gi.verify(expected_arch="gfx1100")
    assert r["status"] == "GPU_UNAVAILABLE"
    assert "torch runtime unusable" in r["reason"]
    # explicit test-mode authorization covers torch-less stub stacks (CI);
    # still never a GPU PASS
    r2 = gi.verify(expected_arch="gfx1100", cpu_authorized=True)
    assert r2["status"] == "CPU_TEST_MODE_AUTHORIZED"
    assert r2["ok"] is True
    assert "never a GPU PASS" in r2["reason"]


def test_probe_wrong_result_fails(tmp_path):
    _root, sysr, dri = single(tmp_path)
    ns = fake_torch()

    class Bad(FakeTensor):
        def __getitem__(self, key):
            # tuple index (result element) returns a WRONG value; int index
            # (input row) returns the input value
            v = 0.5 if isinstance(key, tuple) else 3.0
            return FakeTensor("cuda:0", v)

        def __matmul__(self, o):
            return Bad("cuda:0", 3.0)
    ns.randn = lambda *a, device=None, dtype=None: Bad(f"{device._s}")
    r = gi.verify(expected_arch="gfx1100", torch_ns=ns, sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_FAILED"
    assert "mismatch" in r["reason"]


def test_arch_list_handles_suffixes():
    assert gi._arch_list("gfx1100:sramecc+:xnack-") == ["gfx1100"]
    assert gi._arch_list("gfx1100") == ["gfx1100"]
    assert gi._arch_list(None) == []


def test_bdf_normalization():
    assert gi.bdf_matches("0000:0b:00.0", "0b:00.0")
    assert gi.bdf_matches("0b:00.0", "0000:0b:00.0")
    assert not gi.bdf_matches("0000:0b:00.0", "0000:0c:00.0")


def test_cli_exit_codes(monkeypatch, capsys):
    fake = fake_torch()
    monkeypatch.setattr(gi, "_load_torch", lambda: fake)
    # CLI uses the REAL sysfs: a fake namespace with PCI ids cannot bind to
    # this host's PCI tree, which must surface as a fail-closed mismatch.
    rc = gi.main(["verify", "--expect-arch", "gfx1100", "--skip-probe"])
    out = json.loads(capsys.readouterr().out)
    assert rc == (0 if out["status"] == "GPU_EXECUTION_UNVERIFIED" else 3)
    assert out["status"] in ("GPU_EXECUTION_UNVERIFIED", "GPU_DEVICE_MISMATCH")
    rc = gi.main(["verify", "--expect-arch", "gfx1200"])
    assert rc == 3


def test_cli_exit_codes_with_fake_sysfs(tmp_path, monkeypatch, capsys):
    _root, sysr, dri = single(tmp_path)
    monkeypatch.setattr(gi, "_load_torch", lambda: fake_torch())
    rc = gi.main(["verify", "--expect-arch", "gfx1100", "--skip-probe",
                  "--sys-root", sysr, "--dev-dri", dri])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "GPU_EXECUTION_UNVERIFIED"
    assert out["device"]["pci_bdf"] == "0000:23:00.0"
    rc = gi.main(["verify", "--expect-arch", "gfx1100", "--sys-root", sysr,
                  "--dev-dri", dri])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "GPU_EXECUTION_VERIFIED"


def test_cli_gpu_unavailable_rc4(monkeypatch):
    monkeypatch.setattr(gi, "_load_torch", lambda: fake_torch(available=False))
    assert gi.main(["verify", "--expect-arch", "gfx1100"]) == 4
    assert gi.main(["verify", "--expect-arch", "gfx1100", "--allow-cpu"]) == 0


# ----------------------------------------------- RC5 M1.4 physical binding
def test_first_amdgpu_card_fallback_is_gone():
    """The RC4.1 fallback returned the first amdgpu card's PCI slot: a guess
    on multi-GPU hosts and plainly wrong in a container given GPU #5 of 8."""
    assert not hasattr(gi, "sysfs_bdf_for_device")


def test_framework_without_pci_ids_fails_closed(tmp_path):
    _root, sysr, dri = single(tmp_path)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(pci_ids=False),
                  run_probe=False, sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert "no PCI ids" in r["reason"]
    assert r["device"]["pci_bdf"] is None


def test_container_given_gpu5_of_8_binds_the_exposed_device(tmp_path):
    """sysfs lists eight identical gfx1100 cards; the container may only use
    renderD133 (0000:a3:00.0). Index 0 must bind to THAT card, not to the
    first one in /sys/class/drm (0000:03:00.0)."""
    root = tmp_path / "fs"
    gpus = []
    for n, bus in enumerate([0x03, 0x23, 0x43, 0x63, 0x83, 0xA3, 0xC3, 0xE3]):
        g = {"dom": 0, "bus": bus, "dev": 0, "fn": 0, "device_id": 0x744B,
             "minor": 128 + n, "unique": f"{bus:012x}aa01", "kfd_node": str(n + 2),
             "card": n + 1}
        gpus.append(g)
        write_gpu_sysfs(root, g, exposed=[f"renderD{128 + 5}"])
    want = gpus[5]
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(gpu=want),
                  run_probe=False, sys_root=str(root / "sys"),
                  dev_dri=str(root / "dev/dri"))
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED", r.get("reason")
    assert r["bound_bdf"] == "0000:a3:00.0"
    assert r["device"]["drm_render_node"] == "renderD133"
    # claiming the FIRST card's address for this device is a mismatch
    r2 = gi.verify(expected_arch="gfx1100", expected_bdf="0000:03:00.0",
                   torch_ns=fake_torch(gpu=want), run_probe=False,
                   sys_root=str(root / "sys"), dev_dri=str(root / "dev/dri"))
    assert r2["status"] == "GPU_DEVICE_MISMATCH"


def test_multi_gpu_same_arch_disambiguated_by_bdf(tmp_path):
    """Two identical GPUs, both visible: each index binds to its own slot."""
    root = tmp_path / "fs"
    g0 = dict(GPU5, bus=0x03, minor=128, unique="e9d0e20bb686e6c6", kfd_node="2",
              card=1)
    g1 = dict(GPU5, bus=0x23, minor=129, unique="7e99b4d2506e050a", kfd_node="3",
              card=2)
    write_gpu_sysfs(root, g0, exposed=["renderD128", "renderD129"])
    write_gpu_sysfs(root, g1, exposed=["renderD128", "renderD129"])
    sysr, dri = str(root / "sys"), str(root / "dev/dri")
    a = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(gpu=g0, device_count=2),
                  device_index=0, run_probe=False, sys_root=sysr, dev_dri=dri)
    b = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(gpu=g1, device_count=2),
                  device_index=1, run_probe=False, sys_root=sysr, dev_dri=dri)
    assert a["bound_bdf"] == "0000:03:00.0"
    assert b["bound_bdf"] == "0000:23:00.0"
    # asking for GPU 1's address while framework index 0 is GPU 0 -> mismatch
    c = gi.verify(expected_arch="gfx1100", expected_bdf="0000:23:00.0",
                  torch_ns=fake_torch(gpu=g0, device_count=2), run_probe=False,
                  sys_root=sysr, dev_dri=dri)
    assert c["status"] == "GPU_DEVICE_MISMATCH"


def test_device_count_mismatch_is_ambiguous(tmp_path):
    """Framework reports two devices but the container exposes one render
    node: the index->device mapping cannot be trusted -> fail closed."""
    root = tmp_path / "fs"
    g0 = dict(GPU5, bus=0x03, minor=128, kfd_node="2", card=1)
    g1 = dict(GPU5, bus=0x23, minor=129, kfd_node="3", card=2)
    write_gpu_sysfs(root, g0, exposed=["renderD128"])
    write_gpu_sysfs(root, g1, exposed=["renderD128"], kfd=False)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(gpu=g0, device_count=2),
                  run_probe=False, sys_root=str(root / "sys"),
                  dev_dri=str(root / "dev/dri"))
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert "ambiguous device mapping" in r["reason"]


def test_second_pci_function_audio_is_not_the_gpu(tmp_path):
    """A Radeon occupies 03:00.0 (GPU, class 0x03) and 03:00.1 (HDMI audio,
    class 0x04); HIP only reports bus/device. The display-class function is
    the GPU (found on the real W7900: the first strict rule rejected it)."""
    _root, sysr, dri = single(tmp_path, fn_audio=True)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(), run_probe=False,
                  sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED"
    assert r["bound_bdf"].endswith(".0")


def test_two_display_class_functions_are_ambiguous(tmp_path):
    root = tmp_path / "fs"
    write_gpu_sysfs(root, GPU5, exposed=["renderD129"])
    aud = root / "sys/bus/pci/devices/0000:23:00.1"
    aud.mkdir()
    (aud / "class").write_text("0x030200\n")  # another display controller
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(), run_probe=False,
                  sys_root=str(root / "sys"), dev_dri=str(root / "dev/dri"))
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert "display-class" in r["reason"]


def test_render_node_not_exposed_to_container(tmp_path):
    root = tmp_path / "fs"
    write_gpu_sysfs(root, GPU5, exposed=["renderD128"])  # some OTHER device
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(), run_probe=False,
                  sys_root=str(root / "sys"), dev_dri=str(root / "dev/dri"))
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert "not exposed" in r["reason"]


def test_unique_id_mismatch_fails_closed(tmp_path):
    _root, sysr, dri = single(tmp_path, unique="0" * 16)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(), run_probe=False,
                  sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert "unique id mismatch" in r["reason"]


def test_missing_unique_id_is_unknown_not_fatal(tmp_path):
    _root, sysr, dri = single(tmp_path, unique=None)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(), run_probe=False,
                  sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED"
    assert r["device"]["uuid_consistent"] is None


def test_kfd_device_id_mismatch_fails_closed(tmp_path):
    _root, sysr, dri = single(tmp_path, kfd_device_id=0x744C)
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(), run_probe=False,
                  sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert "KFD node" in r["reason"]


def test_kfd_nodes_of_other_tenants_unreadable_are_disclosed(tmp_path):
    """On the real host nodes 3..9 belong to GPUs outside the container and
    raise PermissionError; they are skipped and the count is disclosed."""
    _root, sysr, dri = single(tmp_path)
    foreign = Path(sysr) / "class/kfd/kfd/topology/nodes/7"
    foreign.mkdir(parents=True)
    (foreign / "properties").write_text("device_id 1\ndrm_render_minor 200\n")
    (foreign / "properties").chmod(0o000)
    if os.access(foreign / "properties", os.R_OK):  # running as root
        pytest.skip("root can read mode-000 files; covered on the real host")
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(), run_probe=False,
                  sys_root=sysr, dev_dri=dri)
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED"
    assert r["device"]["kfd_nodes_unreadable"] == 1


def test_uuid_forms_roundtrip():
    assert gi.uuid_consistent("65396430-6532-3062-6236-383665366336",
                              "e9d0e20bb686e6c6") is True
    assert gi.uuid_consistent("e9d0e20bb686e6c6", "e9d0e20bb686e6c6") is True
    assert gi.uuid_consistent("65396430-6532-3062-6236-383665366336",
                              "0" * 16) is False
    assert gi.uuid_consistent(None, "abc") is None


# --------------------------------------------- RC5 M1.2 probe hard timeout
def test_probe_hard_timeout_terminates_hung_child(monkeypatch):
    """A probe child that hangs is stopped at a REAL wall-clock deadline."""
    monkeypatch.setenv(gi.CHILD_MODE_ENV, "hang")
    t0 = time.monotonic()
    with pytest.raises(gi.ProbeTimeout) as ei:
        gi.probe_isolated(0, budget_s=2.0, card=None)
    wall = time.monotonic() - t0
    ev = ei.value.evidence
    assert isinstance(ei.value, TimeoutError)
    assert ev["child_end_state"] in ("terminated_by_sigterm", "killed_by_sigkill")
    assert ev["child_reaped"] is True
    assert ev["gpu_state_after_timeout"] == "UNKNOWN"  # no card -> no claim
    assert 2.0 <= wall < 30.0
    # the hung child is really gone
    assert not Path(f"/proc/{ev['child_pid']}").exists() or \
        gi.Path(f"/proc/{ev['child_pid']}/stat").read_text().rpartition(")")[2].split()[0] == "Z"


def test_probe_child_failure_is_execution_failed(monkeypatch):
    monkeypatch.setenv(gi.CHILD_MODE_ENV, "fail")
    with pytest.raises(RuntimeError, match="probe child rc=1"):
        gi.probe_isolated(0, budget_s=60.0, card=None)


BOUND = {"pci_bdf": "0000:23:00.0", "drm_card": "card35", "drm_render_node": "renderD129",
         "drm_render_minor": 129, "kfd_node": "3", "sysfs_unique_id": GPU5["unique"],
         "framework_uuid": _ascii_uuid(GPU5["unique"]), "uuid_consistent": True,
         "exposed_render_nodes": ["renderD129"], "framework_device_count": 1,
         "binding_chain": ["stubbed-for-unit-test"]}


def _real_torch_fake(monkeypatch, **torch_kw):
    """A fake torch that is NOT injected through verify(torch_ns=...): verify()
    sees a 'real' runtime and must therefore use the isolated probe."""
    monkeypatch.setattr(gi, "_load_torch", lambda: fake_torch(**torch_kw))
    monkeypatch.setattr(gi, "bind_pci_identity", lambda *a, **k: dict(BOUND))


def test_verify_maps_probe_timeout_to_progress_timeout(tmp_path, monkeypatch):
    _real_torch_fake(monkeypatch)

    def raise_it(*a, **k):
        raise gi.ProbeTimeout("probe exceeded 60s", {
            "child_end_state": "terminated_by_sigterm", "child_reaped": True,
            "gpu_state_after_timeout": "VRAM_RELEASED"})
    monkeypatch.setattr(gi, "probe_isolated", raise_it)
    r = gi.verify(expected_arch="gfx1100", receipt_path=tmp_path / "r.json")
    assert r["status"] == "GPU_PROGRESS_TIMEOUT"
    assert r["ok"] is False
    assert r["verdict"] == "FAIL"
    assert r["probe_timeout_evidence"]["child_reaped"] is True
    assert "device_state" not in r  # the device recovered
    assert json.loads((tmp_path / "r.json").read_text())["status"] == \
        "GPU_PROGRESS_TIMEOUT"


def test_verify_timeout_with_unrecovered_device_is_blocked(monkeypatch):
    _real_torch_fake(monkeypatch)

    def raise_it(*a, **k):
        raise gi.ProbeTimeout("probe exceeded 60s", {
            "child_end_state": "UNINTERRUPTIBLE", "child_reaped": False,
            "gpu_state_after_timeout": "VRAM_NOT_RELEASED"})
    monkeypatch.setattr(gi, "probe_isolated", raise_it)
    r = gi.verify(expected_arch="gfx1100")
    assert r["status"] == "GPU_PROGRESS_TIMEOUT"
    assert r["device_state"] == "BLOCKED"
    assert "BLOCKED" in r["reason"]
    assert gi.EXIT_BY_STATUS["GPU_PROGRESS_TIMEOUT"] == 5


def test_verify_probe_exception_is_execution_failed(monkeypatch):
    _real_torch_fake(monkeypatch)

    def raise_it(*a, **k):
        raise RuntimeError("probe child rc=1: HIP error")
    monkeypatch.setattr(gi, "probe_isolated", raise_it)
    r = gi.verify(expected_arch="gfx1100")
    assert r["status"] == "GPU_EXECUTION_FAILED"
    assert r["ok"] is False


def test_real_torch_never_uses_in_process_probe(tmp_path, monkeypatch):
    """With a real (non-injected) torch the probe MUST be the isolated one:
    the in-process path cannot be interrupted and is test-only."""
    calls = []
    monkeypatch.setattr(gi, "probe_isolated",
                        lambda *a, **k: calls.append(k) or {"probe": "stub"})
    monkeypatch.setattr(gi, "probe_compute",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("in-process probe used")))
    _real_torch_fake(monkeypatch)
    r = gi.verify(expected_arch="gfx1100")
    assert r["status"] == "GPU_EXECUTION_VERIFIED"
    assert len(calls) == 1  # isolated path taken exactly once
