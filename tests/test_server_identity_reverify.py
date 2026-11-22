"""server_identity stop-path unit tests (RC2 mutation control A8).

The pre-signal re-verification in cmd_stop (before EACH of SIGINT/SIGTERM) is
defense-in-depth against PID replacement between the first verification and
the signal. Removing it previously survived the whole 16-scenario lifecycle
suite — these tests pin it.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "server_identity_mod", REPO / "scripts" / "server_identity.py")
si = importlib.util.module_from_spec(spec)
spec.loader.exec_module(si)


def _args(receipt, timeout=0.1):
    return argparse.Namespace(receipt=str(receipt), proc_root="/proc",
                              require_idle=False, dry_run=False,
                              timeout=timeout)


RECEIPT = {
    "pid": 424242,
    "uid": 0,
    "starttime": "12345",
    "argv_sha256": "0" * 64,
    "port": 31000,
    "skip_socket_check": True,
}


def test_stop_reverifies_before_each_signal(tmp_path, monkeypatch):
    """A pid that verifies once but is REPLACED before the second signal must
    cause a refusal (IdentError), never a blind signal to a reused pid."""
    calls = {"verify": 0, "signals": []}
    monkeypatch.setattr(si, "load_receipt", lambda p: dict(RECEIPT))
    monkeypatch.setattr(si, "established_count", lambda root, port: 0)

    def verify_process(*a, **k):
        calls["verify"] += 1
        if calls["verify"] <= 2:
            # pre-loop check + pre-SIGINT check pass; pre-SIGTERM catches
            # a pid that was REPLACED after SIGINT was delivered
            return {"pid": RECEIPT["pid"], "state": "S", "uid": "0",
                    "starttime": RECEIPT["starttime"], "argv": ["x"],
                    "argv_sha256": RECEIPT["argv_sha256"]}
        raise si.IdentError(2, "pid replaced between signals (test)")

    monkeypatch.setattr(si, "verify_process", verify_process)
    monkeypatch.setattr(si, "send_signal",
                        lambda pid, sig: calls["signals"].append(sig.name))
    monkeypatch.setattr(si, "wait_gone",
                        lambda root, pid, t, poll=None: "alive")
    rcpt = tmp_path / "server-identity.json"
    with pytest.raises(si.IdentError) as ei:
        si.cmd_stop(_args(rcpt))
    assert ei.value.code == 2
    # exactly one signal was sent; the second was blocked by re-verification
    assert calls["signals"] == ["SIGINT"]


def test_stop_signal_sequence_when_verification_keeps_passing(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "load_receipt", lambda p: dict(RECEIPT))
    monkeypatch.setattr(si, "established_count", lambda root, port: 0)

    def verify_process(*a, **k):
        return {"pid": RECEIPT["pid"], "state": "S", "uid": "0",
                "starttime": RECEIPT["starttime"], "argv": ["x"],
                "argv_sha256": RECEIPT["argv_sha256"]}

    signals = []
    monkeypatch.setattr(si, "verify_process", verify_process)
    monkeypatch.setattr(si, "send_signal",
                        lambda pid, sig: signals.append(sig.name))
    monkeypatch.setattr(si, "wait_gone",
                        lambda root, pid, t, poll=None: "alive")
    rcpt = tmp_path / "server-identity.json"
    with pytest.raises(si.IdentError) as ei:
        si.cmd_stop(_args(rcpt))
    assert ei.value.code == 5  # BLOCKED after both signals — never SIGKILL
    assert signals == ["SIGINT", "SIGTERM"]
