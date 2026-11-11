"""Documentation command contract tests (Issue D).

Every runnable command shown in the top-line developer docs must reference
files that exist and parse. This prevents the classic release defect of a
README Quick Start that cannot execute from a fresh clone.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

DOC_FILES = [
    "README.md",
    "docs/QUICKSTART_W7900.md",
    "docs/ROCM_INSTALLATION.md",
    "docs/BENCHMARK_REPRODUCTION.md",
    "docs/TROUBLESHOOTING.md",
]

# Scripts whose --help must succeed (import-safe, no workspace/GPU needed)
HELP_SAFE = {
    "check_environment.py", "download_pins.py", "yue2_workspace.py",
    "checkpoint_wsb.py", "collect_performance.py", "resume_wsb.py",
    "verify_wsb_artifacts.py", "per_parity_study.py", "scoring_stage_check.py",
    "server_identity.py",
}


def _bash_blocks(text: str):
    for m in re.finditer(r"```bash\n(.*?)```", text, re.S):
        yield from m.group(1).splitlines()


def _repo_script_refs(lines):
    for line in lines:
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        for m in re.finditer(r"(?:^|\s|/)(scripts/[\w./-]+)", line + " "):
            yield m.group(1)


@pytest.mark.parametrize("doc", DOC_FILES)
def test_documented_scripts_exist(doc):
    path = REPO / doc
    if not path.is_file():
        pytest.skip(f"{doc} not present in this checkout")
    refs = set(_repo_script_refs(_bash_blocks(path.read_text(encoding="utf-8"))))
    missing = [r for r in refs if not (REPO / r).is_file()]
    assert not missing, f"{doc} references nonexistent scripts: {missing}"


@pytest.mark.parametrize("doc", DOC_FILES)
def test_documented_shell_scripts_parse(doc):
    path = REPO / doc
    if not path.is_file():
        pytest.skip(f"{doc} not present in this checkout")
    refs = {r for r in _repo_script_refs(_bash_blocks(path.read_text(encoding="utf-8")))
            if r.endswith(".sh") and (REPO / r).is_file()}
    for ref in sorted(refs):
        proc = subprocess.run(["bash", "-n", str(REPO / ref)],
                              capture_output=True, text=True)
        assert proc.returncode == 0, f"bash -n failed for {ref}: {proc.stderr}"


def test_help_safe_scripts_expose_help():
    for name in sorted(HELP_SAFE):
        script = REPO / "scripts" / name
        if not script.is_file():
            continue
        proc = subprocess.run([sys.executable, str(script), "--help"],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"{name} --help failed: {proc.stderr[-400:]}"


def test_readme_quickstart_uses_env_not_machine_paths():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    blocks = "\n".join(_bash_blocks(text))
    assert "/home/amd" not in blocks, "README runnable blocks must not embed machine paths"
    assert "/raid/" not in blocks and "/tmp/opencode" not in blocks


def test_no_documented_curl_pipe_bash():
    for doc in DOC_FILES:
        path = REPO / doc
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for line in _bash_blocks(text):
            assert not re.search(r"curl[^|]*\|\s*(sudo\s+)?(ba)?sh", line), \
                f"{doc}: curl|bash is forbidden"
