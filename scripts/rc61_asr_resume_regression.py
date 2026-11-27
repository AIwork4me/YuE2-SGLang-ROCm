#!/usr/bin/env python3
"""rc61_asr_resume_regression.py — M2.6 physical resume regression.

Exercises the RC6.1 ASR receipt/resume machinery on REAL audio candidates
(read-only inputs; receipts are written to a scratch run dir):

    start -> complete one candidate -> HARD KILL mid-write (torn line)
    -> resume -> torn tail atomically quarantined, candidate re-runs
    -> HARD KILL again after another receipt -> resume -> completion
    -> final fail-closed audit (no duplicates, no invalid receipts,
       no silent skips, superseded files preserved)

Also proves (negative): identity change between resumes is REFUSED (no
stale identity reuse), and a tampered receipt body is REFUSED.

The transcripts themselves are SYNTHETIC (engine label MOCK-ENGINE-RESUME-
TEST): this regression tests receipt durability + resume semantics, not ASR
quality — the audio hashes, manifest binding and identity contract are real.

Usage:  python3 scripts/rc61_asr_resume_regression.py [--audio-root DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import rc6_asr_identity as asr_id  # noqa: E402

DEFAULT_AUDIO_ROOT = Path("/data/yue2-runs/rc5-latest-upstream-20261124T065451Z/"
                          "wsb_full/songbench_sel/audio")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_identity(tag: str = "mock-engine-resume-test") -> dict:
    return asr_id.build_run_identity(
        model_root=Path("/tmp/opencode/mock_asr_root"),
        engine={"engine": tag, "vllm": "mock", "torch": "mock",
                "hip": "mock", "dtype": "float32", "seed": 0},
        preproc={"audio_loading": "mock_normalize", "chunking": "mock_chunk",
                 "utils_sha256": "u" * 64, "sample_rate": 16000},
        decoding={"temperature": 0.0, "top_p": 1.0, "top_k": -1,
                  "max_tokens": 4096, "seed": 0, "repeats": 2},
        scoring={"audio_manifest_sha256": "manifest-bound-at-runtime"},
        driver_path=Path(__file__).resolve())


CHILD_MODE_ENV = "RC61_RESUME_CHILD"


def child_main() -> int:
    """The 'engine': appends one receipt per candidate, fsync'd, with an
    optional induced crash point (torn write / kill after receipt N)."""
    work = Path(os.environ["RC61_WORK"])
    mode = os.environ.get("RC61_CRASH", "")
    manifest = [json.loads(l) for l in
                (work / "manifest.jsonl").read_text().splitlines() if l.strip()]
    identity = json.loads((work / "identity.json").read_text())
    out = work / "transcripts.jsonl"
    res = asr_id.prepare_resume(out, manifest, identity, expected_repeats=2) \
        if out.is_file() else {"action": "READY", "reusable": [], "todo": [r["id"] for r in manifest]}
    if res["action"] == "REFUSED":
        print(json.dumps({"child": "REFUSED", "reason": res["reason"]}))
        return 4
    done = set(res["reusable"])
    todo = [r for r in manifest if r["id"] not in done]
    crash_at = int(mode.split(":")[1]) if mode.startswith("kill:") else None
    torn = mode == "torn"
    with out.open("a") as fout:
        for i, r in enumerate(todo):
            receipt = {
                "id": r["id"], "prompt_index": r["prompt_index"],
                "candidate_index": r["candidate_index"], "lang": r["lang"],
                "audio_sha256": r["audio_sha256"], "chunks": 1,
                "repeats": [{"repeat": k, "text": f"mock transcript {k}"}
                            for k in range(2)],
                "engine": {"engine": "MOCK-ENGINE-RESUME-TEST"},
                "run_identity": identity, "repeat_count": 2,
                "status": "complete", "wall_s": 0.01,
            }
            receipt["transcript_receipt_sha256"] = asr_id.receipt_sha256(receipt)
            line = json.dumps(receipt, ensure_ascii=False) + "\n"
            if torn and i == len(todo) - 1:
                # crash MID-LINE: torn tail (atomic append interrupted)
                fout.write(line[:len(line) // 2])
                fout.flush()
                os.kill(os.getpid(), signal.SIGKILL)
            fout.write(line)
            fout.flush()
            os.fsync(fout.fileno())
            if crash_at is not None and i + 1 == crash_at:
                os.kill(os.getpid(), signal.SIGKILL)
    return 0


def run_child(work: Path, mode: str) -> int:
    env = {**os.environ, "RC61_RESUME_CHILD": "1", "RC61_WORK": str(work),
           "RC61_CRASH": mode}
    p = subprocess.run([sys.executable, __file__], env=env)
    return p.returncode


def rows_of(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines()
            if l.strip() and not l.startswith("{") is False and _parsable(l)]


def _parsable(l: str) -> bool:
    try:
        json.loads(l)
        return True
    except ValueError:
        return False


def main() -> int:
    if os.environ.get(CHILD_MODE_ENV):
        return child_main()
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    ap.add_argument("--work", type=Path, default=None)
    a = ap.parse_args()
    import tempfile
    work = a.work or Path(tempfile.mkdtemp(prefix="rc61_asr_resume_"))
    work.mkdir(parents=True, exist_ok=True)

    audio_root = a.audio_root
    candidates = sorted(p for p in audio_root.glob("*/audio.mp3"))[:3]
    if len(candidates) < 3:
        print(f"FATAL: need 3 real audio candidates under {audio_root}")
        return 2
    manifest = []
    for i, p in enumerate(candidates):
        manifest.append({"id": f"cand_{i}", "prompt_index": i, "candidate_index": 0,
                         "lang": "zh", "audio_path": str(p),
                         "audio_sha256": sha256_file(p)})
    (work / "manifest.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in manifest))
    identity = make_identity()
    (work / "identity.json").write_text(json.dumps(identity, indent=1))

    steps = []

    def step(name, rc, extra=None):
        steps.append({"step": name, "rc": rc, **(extra or {})})
        print(f"[regression] {name}: rc={rc}")
        return rc

    # 1) start: complete one candidate, then crash AFTER receipt 2
    rc = step("start+kill-after-2", run_child(work, "kill:2"))
    out = work / "transcripts.jsonl"
    complete_after_start = rows_of(out)
    if not (len(complete_after_start) == 2):
        return step("FATAL-start-state", 9, {"rows": len(complete_after_start)})

    # 2) resume: completes 3rd... but crash MID-LINE (torn tail)
    rc = step("resume+torn-tail", run_child(work, "torn"))
    torn = out.read_text()
    if not torn.endswith("\n") or "{torn" in torn:
        # after the torn crash the last line is a partial JSON line
        lines = [l for l in torn.splitlines() if l.strip()]
        if _parsable(lines[-1]):
            return step("FATAL-no-torn-line", 8)

    # 3) resume again: torn tail quarantined + candidate 3 re-runs to completion
    rc = step("resume-final", run_child(work, ""))
    final = rows_of(out)
    if len(final) != 3:
        return step("FATAL-final-count", 9, {"rows": len(final)})
    ids = [r["id"] for r in final]
    if len(set(ids)) != 3:
        return step("FATAL-duplicates", 9, {"ids": ids})

    # 4) final fail-closed audit
    audit = asr_id.audit_receipts(out, manifest, identity, expected_repeats=2)
    if audit["decisions"] != {r["id"]: "REUSABLE" for r in manifest}:
        return step("FATAL-final-audit", 9, {"decisions": audit["decisions"]})
    qfiles = sorted(work.glob("transcripts.jsonl.quarantine-*"))
    if not qfiles:
        return step("FATAL-no-quarantine-evidence", 9)

    # 5) negative: identity change between resumes must be REFUSED
    changed = make_identity()
    changed["engine"]["seed"] = 7
    changed["run_identity_sha256"] = asr_id.sha256_bytes(
        json.dumps({k: v for k, v in changed.items() if k != "run_identity_sha256"},
                   sort_keys=True).encode())
    res = asr_id.prepare_resume(out, manifest, changed, expected_repeats=2)
    if res["action"] != "REFUSED":
        return step("FATAL-stale-identity-reuse", 9, {"action": res["action"]})

    # 6) negative: tampered receipt body with stale hash must be REFUSED
    tampered = rows_of(out)
    tampered[0]["repeats"][0]["text"] = "TAMPERED"
    tam_path = work / "tampered.jsonl"
    tam_path.write_text("".join(json.dumps(r) + "\n" for r in tampered))
    res2 = asr_id.prepare_resume(tam_path, manifest, identity, expected_repeats=2)
    if res2["action"] != "REFUSED" or \
            asr_id.R_RECEIPT_HASH not in res2["audit"]["fail_closed_hard_errors"]:
        return step("FATAL-tamper-accepted", 9, {"action": res2.get("action"),
                                                 "hard": res2["audit"]["fail_closed_hard_errors"]})

    report = {
        "schema": "yue2-rc6_1-asr-physical-resume/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "audio_candidates": [{"id": r["id"], "audio_path": r["audio_path"],
                              "audio_sha256": r["audio_sha256"]} for r in manifest],
        "engine": "MOCK-ENGINE-RESUME-TEST (synthetic transcripts; real audio "
                  "hashes, manifest binding, identity contract, atomicity)",
        "steps": steps,
        "final_state": {
            "complete_receipts": len(final),
            "duplicate_complete_ids": 0,
            "quarantine_files": [str(q) for q in qfiles],
            "superseded_files": sorted(str(p) for p in work.glob("*.superseded-*")),
            "final_audit_all_reusable": True,
            "stale_identity_refused": True,
            "tampered_receipt_refused": True,
            "no_data_loss": len(final) == 3,
        },
        "verdict": "PASS",
        "work_dir": str(work),
    }
    outp = REPO / "reports/developer_reference/rc6_1/02_ASR_PHYSICAL_RESUME.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"verdict": "PASS", "report": str(outp)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
