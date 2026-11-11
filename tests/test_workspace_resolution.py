"""Regression tests for the single workspace resolution contract.

Historical defect (mission Issue A): scripts defaulted to
``Path(__file__).resolve().parents[2]``, which is one directory ABOVE a
standalone clone — silently producing a wrong workspace on fresh checkouts.
These tests pin the corrected contract in scripts/yue2_workspace.py.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from yue2_workspace import resolve_workspace  # noqa: E402


def _make_workspace(root: Path, with_assets: bool = True) -> Path:
    (root / "benchmark" / "WildSongBench").mkdir(parents=True, exist_ok=True)
    if with_assets:
        (root / "models").mkdir(exist_ok=True)
    return root


def _script_in(repo: Path) -> Path:
    d = repo / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    return d / "anything.py"


def test_standalone_clone_resolves_repo_root(tmp_path, monkeypatch):
    monkeypatch.delenv("YUE2_WORKSPACE", raising=False)
    repo = tmp_path / "YuE2-SGLang-ROCm"
    repo.mkdir()
    _make_workspace(repo)          # assets placed in the repo root
    script = _script_in(repo)
    assert resolve_workspace(script) == repo


def test_historical_nested_layout_still_supported(tmp_path, monkeypatch):
    monkeypatch.delenv("YUE2_WORKSPACE", raising=False)
    ws = _make_workspace(tmp_path / "ws")
    repo = tmp_path / "ws" / "YuE2-SGLang-ROCm"   # repo directly under <ws>
    repo.mkdir(parents=True)
    script = _script_in(repo)
    # parents[2] of <ws>/<repo>/scripts/x.py is <ws> — the historical default
    assert resolve_workspace(script) == ws


def test_env_var_overrides(tmp_path, monkeypatch):
    ws = _make_workspace(tmp_path / "explicit")
    repo = tmp_path / "standalone"
    repo.mkdir()
    script = _script_in(repo)
    monkeypatch.setenv("YUE2_WORKSPACE", str(ws))
    assert resolve_workspace(script) == ws


def test_env_var_missing_dir_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("YUE2_WORKSPACE", str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_workspace(_script_in(tmp_path / "repo"))


def test_env_var_non_workspace_errors(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("YUE2_WORKSPACE", str(empty))
    with pytest.raises(FileNotFoundError, match="does not look like"):
        resolve_workspace(_script_in(tmp_path / "repo"))


def test_no_workspace_anywhere_lists_candidates(tmp_path, monkeypatch):
    monkeypatch.delenv("YUE2_WORKSPACE", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    script = _script_in(repo)
    with pytest.raises(FileNotFoundError, match="Candidates considered"):
        resolve_workspace(script)


def test_historical_default_was_wrong_for_standalone_clone(tmp_path):
    """Document the original defect: parents[2] of a standalone clone escapes it."""
    repo = tmp_path / "clone"
    script = _script_in(repo)
    assert script.resolve().parents[2] != repo.resolve()


def test_all_shipped_scripts_use_the_contract():
    offenders = []
    for py in (REPO / "scripts").glob("*.py"):
        if py.name in ("yue2_workspace.py", "download_pins.py"):
            continue  # the contract itself; download_pins bootstraps (documented)
        text = py.read_text(encoding="utf-8")
        if "parents[2]" in text:
            offenders.append(py.name)
    assert not offenders, f"scripts still hard-code parents[2]: {offenders}"


def test_resolver_runs_from_arbitrary_cwd(tmp_path, monkeypatch):
    """Issue A acceptance: resolution must not depend on the current directory."""
    monkeypatch.delenv("YUE2_WORKSPACE", raising=False)
    ws = _make_workspace(tmp_path / "ws")
    repo = tmp_path / "ws" / "YuE2-SGLang-ROCm"
    repo.mkdir(parents=True)
    script = _script_in(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert resolve_workspace(script) == ws
