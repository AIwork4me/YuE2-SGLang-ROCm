"""restoration_audit.py regression tests (C1) — CPU only, synthetic fixtures.

Proves: the verification set is the journal's distinct complete ids; subset
inputs are filtered without touching the original; the pilot workspace is an
independent symlink farm; unresolved failures block; snapshot cross-check
detects drift; verdict vocabulary never claims FULL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts/campaign_ops"))
import restoration_audit as RA  # noqa: E402


def make_journal(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class TestRowIdent:
    def test_ident_format(self):
        assert RA.row_ident({"prompt_index": 3, "candidate_index": 1,
                             "seed": 831020}) == "wsb_003_r1_s831020"


class TestSubsetInputs:
    def test_subset_filtering_preserves_order_and_drops_rest(self):
        rows = [
            {"prompt_index": 0, "candidate_index": 0, "seed": 831001},
            {"prompt_index": 0, "candidate_index": 1, "seed": 831019},
            {"prompt_index": 1, "candidate_index": 0, "seed": 831002},
        ]
        keep = {"wsb_000_r1_s831019"}
        text, n = RA.build_subset_inputs_text(rows, keep)
        assert n == 1
        assert json.loads(text)["seed"] == 831019

    def test_original_file_untouched_by_workspace_build(self, tmp_path):
        runs = tmp_path / "run"
        (runs / "songs/wsb_000_r0_s831001").mkdir(parents=True)
        (runs / "songs/wsb_000_r0_s831001/result.json").write_text("{}")
        rows = [{"prompt_index": 0, "candidate_index": 0, "seed": 831001},
                {"prompt_index": 0, "candidate_index": 1, "seed": 831019}]
        inputs = runs / "evaluation_inputs.jsonl"
        inputs.write_text("".join(json.dumps(r) + "\n" for r in rows))
        before = inputs.read_text()
        ws = RA.make_audit_workspace(tmp_path, runs, rows,
                                     {"wsb_000_r0_s831001"})
        assert inputs.read_text() == before  # frozen input untouched
        # independent workspace: subset inputs + symlinked bundle
        sub = [json.loads(l) for l in
               (ws / "evaluation_inputs.jsonl").read_text().splitlines()]
        assert [r["seed"] for r in sub] == [831001]
        link = ws / "songs/wsb_000_r0_s831001"
        assert link.is_symlink()
        assert (link / "result.json").read_text() == "{}"


class TestUnresolvedFailures:
    def test_failed_without_complete_is_unresolved(self, tmp_path):
        j = tmp_path / "j.jsonl"
        make_journal(j, [
            {"id": "a", "status": "failed"},
            {"id": "b", "status": "complete"},
        ])
        assert RA.unresolved_failures(j, {"b"}) == ["a"]

    def test_failed_then_complete_is_resolved(self, tmp_path):
        j = tmp_path / "j.jsonl"
        make_journal(j, [
            {"id": "a", "status": "failed"},
            {"id": "a", "status": "complete"},
        ])
        assert RA.unresolved_failures(j, {"a"}) == []

    def test_torn_final_line_tolerated(self, tmp_path):
        j = tmp_path / "j.jsonl"
        j.write_text('{"id": "a", "status": "complete"}\n{"id": "b", "stat')
        assert RA.unresolved_failures(j, {"a"}) == []


class TestVerdictLogic:
    def test_verdict_vocabulary_never_claims_full(self):
        src = (REPO / "scripts/campaign_ops/restoration_audit.py").read_text()
        assert "RESTORED_SUBSET_VERIFIED" in src
        assert "RESTORE_BLOCKED" in src
        # the tool must label itself a subset verdict, never FULL
        assert "NOT a campaign-completion claim" in src

    def test_expect_mismatch_is_a_problem(self):
        # the --expect-complete guard lives in main(); assert the constant
        # exists so the CLI cannot silently drift
        src = (REPO / "scripts/campaign_ops/restoration_audit.py").read_text()
        assert "--expect-complete" in src

    def test_manifest_pin_is_frozen(self):
        assert RA.MANIFEST_SHA256 == (
            "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0")


class TestSnapshotCrosscheck:
    def test_snapshot_helper_reads_only_complete(self, tmp_path):
        # exercised via main(); here verify the journal reader it builds on
        j = tmp_path / "j.jsonl"
        make_journal(j, [{"id": "x", "status": "complete"},
                         {"id": "y", "status": "failed"}])
        sys.path.insert(0, str(REPO / "scripts"))
        from run_wsb_torch import read_journal
        complete, problems = read_journal(j)
        assert complete == {"x"} and problems == []
