"""gpu_identity.py unit tests (RC4.1 M1.4 CPU/mock verification matrix).

Covers the fail-loud contract states with a fake torch namespace (no GPU, no
torch import required). Real-W7900 verification is a separate hardware gate
(reports/w7900_rc4_1/01_*).
"""
from __future__ import annotations

import importlib.util
import json
import sys
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

    def __matmul__(self, other):
        return self


def fake_torch(available=True, arch="gfx1100", name="AMD Radeon PRO W7900D",
               hip="7.14.60850", cuda_ns=None, version="2.12.0+rocm7.14.1",
               total_memory=51_522_830_336):
    ns = types.SimpleNamespace()
    ns.__version__ = version
    ns.version = types.SimpleNamespace(hip=hip, cuda=cuda_ns)
    ns.cuda = types.SimpleNamespace()
    ns.cuda.is_available = lambda: available
    if available:
        props = types.SimpleNamespace(gcnArchName=arch, name=name,
                                      total_memory=total_memory)
        ns.cuda.get_device_properties = lambda i: props
    ns.device = lambda s: types.SimpleNamespace(_s=s)
    ns.randn = lambda *a, device=None, dtype=None: FakeMatmulTensor(
        f"{device._s}")
    ns.float32 = "fp32"
    ns.cuda.synchronize = lambda i: None
    return ns


def test_happy_path_execution_verified(tmp_path):
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(),
                  receipt_path=tmp_path / "r.json")
    assert r["status"] == "GPU_EXECUTION_VERIFIED"
    assert r["ok"] is True
    assert r["device"]["total_memory_gib"] == 47.98
    written = json.loads((tmp_path / "r.json").read_text())
    assert written["status"] == "GPU_EXECUTION_VERIFIED"
    assert written["worker"]["pid"] > 0
    assert written["framework"]["hip_version"] == "7.14.60850"


def test_arch_mismatch_fails_loud(tmp_path):
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(arch="gfx1151"))
    assert r["status"] == "GPU_DEVICE_MISMATCH"
    assert r["ok"] is False
    assert "gfx1151" in r["reason"]


def test_cuda_only_build_rejected(tmp_path):
    r = gi.verify(expected_arch="gfx1100",
                  torch_ns=fake_torch(cuda_ns="12.4"))
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
    r = gi.verify(expected_arch="gfx1100", expected_bdf="0000:ff:00.0",
                  torch_ns=fake_torch(), run_probe=False)
    # no sysfs fallback on this host fact: BDF unknown -> mismatch (fail loud)
    assert r["status"] in ("GPU_DEVICE_MISMATCH", "GPU_IDENTITY_VERIFIED")
    if r["status"] == "GPU_DEVICE_MISMATCH":
        assert "PCI BDF" in r["reason"]


def test_matching_bdf_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(gi, "sysfs_bdf_for_device",
                        lambda props: "0000:0b:00.0")
    r = gi.verify(expected_arch="gfx1100", expected_bdf="0b:00.0",
                  torch_ns=fake_torch(), run_probe=False)
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED"
    assert r["ok"] is True


def test_identity_verified_without_probe(tmp_path):
    r = gi.verify(expected_arch="gfx1100", torch_ns=fake_torch(),
                  run_probe=False)
    assert r["status"] == "GPU_EXECUTION_UNVERIFIED"


def test_probe_failure_is_execution_failed(tmp_path):
    ns = fake_torch()
    def boom(*a, **k):
        raise RuntimeError("HIP error: device lost (test)")
    ns.randn = boom
    r = gi.verify(expected_arch="gfx1100", torch_ns=ns)
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
    r = gi.verify(expected_arch="gfx1100", torch_ns=ns)
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


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    fake = fake_torch()
    monkeypatch.setattr(gi, "_load_torch", lambda: fake)
    rc = gi.main(["verify", "--expect-arch", "gfx1100", "--skip-probe"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "GPU_EXECUTION_UNVERIFIED"
    rc = gi.main(["verify", "--expect-arch", "gfx1200"])
    assert rc == 3
    rc = gi.main(["verify", "--expect-arch", "gfx1100"])
    assert rc == 0


def test_cli_gpu_unavailable_rc4(tmp_path, monkeypatch):
    monkeypatch.setattr(gi, "_load_torch", lambda: fake_torch(available=False))
    assert gi.main(["verify", "--expect-arch", "gfx1100"]) == 4
    assert gi.main(["verify", "--expect-arch", "gfx1100", "--allow-cpu"]) == 0
