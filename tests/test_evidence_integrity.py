"""Regression tests: omni_wsb evidence integrity invariants.

These tests freeze the 2026-10-16 evidence reorganization rules:
  1. Pilot artifacts can never be labeled/parsed as FULL-run artifacts.
  2. Every full/ artifact carries the full run_id.
  3. Aggregate counts match the strict audit (384/384, 192 prompts, 5 truncated).
  4. Main-pass and prompt-164-resume sessions stay distinguishable.
  5. SHA256 anchors of original raw artifacts stay stable.
  6. Cross-arm comparisons use the correct metric arm.
  7. Benchmark artifacts must not be overwritten by these invariants
     (byte identity of archived copies vs recorded hashes).

CPU-only; no GPU, no network, no model outputs are recomputed.
"""

import hashlib
import json
from pathlib import Path

import pytest

EVID = Path(__file__).resolve().parents[1] / "evidence" / "omni_wsb"
FULL_RUN_ID = "omniwsb20261014T1323Z"
PILOT_RUN_ID = "omni-pilot10x2"

EXPECTED_ANCHORS = {
    "full/run_config.json": "8eeeb4c46f8aeefdf952875ede08c826c3590c660965422acd84131da7846176",
    "pilot/run_config.json": "17f8a78415f4973f86e7c7fc671b794a8df010b6d6e4dc7e3603d7e44fa44271",
    "pilot/generation_summary.json": "6857977afbeec9049054896a1f805ad1c05efc1c539b16224c745d5014e3665e",
    "pilot/audit.json": "4113e5f27e08ba702923d4577f909ec4883c27009ead454a7be8d13ca109483c",
    "full/aggregate_audit.json": "846717aa973945a3acac517c1d999c3f10c1894027a4ae562eed535116bff0a3",
    "full/main_pass_summary.json": "54f3a80835cebe9ea7ae607d719bf2ae61b9acff701f4a4130f6d7ea39164e24",
    "full/resume_prompt164_summary.json": "31bcb4edec2d3c81e61b10f479a8ccec998f8534d1a77a0ebb4a1b854dab3b0c",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(rel: str):
    return json.loads((EVID / rel).read_text())


# --- 1. pilot vs full identity -------------------------------------------------

def test_pilot_artifacts_are_not_labeled_full():
    assert load("pilot/run_config.json")["run_id"] == PILOT_RUN_ID
    assert load("pilot/audit.json")["mode"] == "pilot"
    assert load("pilot/audit.json")["expected_candidates"] == 20


def test_no_pilot_run_id_in_full_directory():
    for p in sorted((EVID / "full").glob("*.json")):
        text = p.read_text()
        assert PILOT_RUN_ID not in text, f"{p.name} references the pilot run id"


def test_no_top_level_ambiguous_artifacts():
    # the old ambiguous top-level files must be gone
    for name in ("run_config.json", "generation_summary.json", "audit.json",
                 "main_pass_summary.json", "prompt164_serving_disclosure.json"):
        assert not (EVID / name).exists(), f"ambiguous top-level artifact {name} is back"


# --- 2. full artifacts carry the full run id -----------------------------------

def test_full_run_config_identity():
    cfg = load("full/run_config.json")
    assert cfg["run_id"] == FULL_RUN_ID
    assert cfg["dataset_revision"].startswith("m-a-p/WildSongBench@")
    assert cfg["candidates"] == 2


def test_sessions_share_full_run_id():
    assert load("full/main_pass_summary.json")["session"]
    assert load("full/resume_prompt164_summary.json")["run_id"] == FULL_RUN_ID


# --- 3. aggregate counts match strict audit ------------------------------------

def test_aggregate_audit_counts():
    a = load("full/aggregate_audit.json")
    assert a["mode"] == "full"
    assert a["expected_candidates"] == 384
    assert a["verified_complete"] == 384
    assert a["missing_or_invalid"] == 0
    assert a["truncated_but_complete"] == 5
    assert a["unique_prompt_coverage"] == 192
    assert a["verdict"] == "FULL"


def test_scores_summary_counts():
    s = load("scores_summary.json")
    assert s["candidate_count"] == 384
    assert s["prompt_count"] == 192
    assert s["full_192_standard_candidate_coverage"] is True


def test_additional_summary_reuses_selection():
    a = load("additional_summary.json")
    assert a["mode"] == "selected"
    assert a["candidate_count"] == 192
    assert a["selection_candidate_count"] == 384
    assert a["full_192_selected_coverage"] is True


def test_selected_candidates_are_192_unique_prompts():
    sel = load("selected_candidates.json")
    assert len(sel) == 192
    assert len({r["prompt_index"] for r in sel}) == 192
    assert all(r["candidate_index"] in (0, 1) for r in sel)


# --- 4. session distinction ------------------------------------------------------

def test_main_pass_and_resume_are_distinct_sessions():
    main = load("full/main_pass_summary.json")
    assert main["complete"] == 382 and main["failed"] == 2
    assert main["resume_pass"]["complete"] == 2
    resume = load("full/resume_prompt164_summary.json")
    # the on-disk summary is the RESUME session: 384 complete of which 382 resumed
    assert resume["complete"] == 384 and resume["resumed"] == 382
    assert resume["wall_s"] == pytest.approx(828.2, abs=0.1)
    assert main["wall_s"] > 80000  # 83,989 s main pass must not be conflated


def test_sessions_add_up():
    main = load("full/main_pass_summary.json")
    resume = load("full/resume_prompt164_summary.json")
    assert main["complete"] + main["failed"] == 384
    assert main["complete"] + resume["complete"] - resume["resumed"] == 384  # 382 + 2


# --- 5. SHA256 anchors stable ----------------------------------------------------

@pytest.mark.parametrize("rel,expected", sorted(EXPECTED_ANCHORS.items()))
def test_sha256_anchor(rel, expected):
    assert sha256(EVID / rel) == expected


def test_anchors_json_matches_full_run_manifest_hashes():
    anchors = load("anchors.json")
    assert anchors["evaluation_inputs"]["sha256"].startswith("a906ab39")
    assert anchors["generation_manifest"]["sha256"].startswith("92ef0148")


# --- 6. cross-arm metric correctness ---------------------------------------------

def test_cross_arm_scores_use_correct_arm():
    s = load("scores_summary.json")
    full_arm = s["unselected_candidates"]["groups"]["all"]
    sel_arm = s["standard_selected"]["groups"]["all"]
    # selected arm must be strictly the PER-selected 192 (better PER by design)
    assert sel_arm["per"]["per_micro"] < full_arm["per"]["per_micro"]
    assert sel_arm["per"]["expected"] == 192
    assert full_arm["per"]["expected"] == 384


def test_songbench_global_averages_are_arm_scoped():
    s = load("scores_summary.json")
    full_ga = s["unselected_candidates"]["groups"]["all"]["songbench"]["means"]["Global Avg"]
    sel_ga = s["standard_selected"]["groups"]["all"]["songbench"]["means"]["Global Avg"]
    assert full_ga == pytest.approx(6.7301, abs=5e-5)
    assert sel_ga == pytest.approx(6.7323, abs=5e-5)
    assert full_ga != sel_ga  # never publish one arm's number as the other's


def test_selected_arm_matches_additional_arm_ids():
    add = load("additional_summary.json")
    sel = load("selected_candidates.json")
    add_sel = add["selected_candidates"]
    assert {(r["prompt_index"], r["candidate_index"]) for r in add_sel} == \
           {(r["prompt_index"], r["candidate_index"]) for r in sel}


# --- 7. evidence manifest consistency (no silent overwrites) ---------------------

def test_evidence_manifest_records_every_file_with_matching_hash():
    m = load("EVIDENCE_MANIFEST.json")
    listed = {f["path"] for f in m["files"]}
    on_disk = {str(p.relative_to(EVID)) for p in EVID.rglob("*")
               if p.is_file() and p.name != "EVIDENCE_MANIFEST.json"}
    # every non-manifest file present on disk is indexed (or intentionally new)
    missing = on_disk - listed
    assert not missing, f"unindexed evidence files: {missing}"
    for f in m["files"]:
        p = EVID / f["path"]
        assert p.exists(), f["path"]
        assert sha256(p) == f["sha256"], f"byte drift: {f['path']}"


def test_source_manifest_wav_counts():
    sm = load("full/source_manifest.json")
    assert sm["run_id"] == FULL_RUN_ID
    assert sm["wav_summary"]["count"] == 384
    assert sm["scores_per_song_rows"] == 384
    assert sm["sessions"]["main_pass"]["complete"] == 382
    assert sm["sessions"]["prompt164_resume"]["complete"] == 2
