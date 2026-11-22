"""RC4 M4.2 — regression: exact official selection tie semantics.

Prompt 19 of armB_full_20261119T015756Z was reported by RC3 as a "PER-equal
tie" where the official evaluator selected r1 and an independent
recomputation selected r0. Root cause (RC4): the official frozen key
(wsb_eval.py select_candidates) is a fully specified 4-tuple

    (per, edits,
     abs(len(asr_repeats[selected_asr_repeat]['phonemes'])
         - reference_phonemes),
     candidate_index)

and for prompt 19 the first two components tie exactly while the third
decides: r1 delta=3 vs r0 delta=11 -> r1 legitimately wins. The independent
scripts per_cross_arm_analysis.py / rc2_per_length_analysis.py carried
unfaithful keys (summed phonemes over ALL repeats / mixed count-vs-rate /
wrong final component) and picked r0.

These tests lock the faithful semantics in:
  1. the prompt-19 numeric scenario selects r1 under the official key;
  2. scripts/per_cross_arm_analysis.py::sel_key is component-identical to
     the official key on randomized synthetic rows (mutation-sensitive);
  3. a frozen-receipt check (192/192 identity match) runs when the frozen
     evidence tree is present and is skipped otherwise.

All fixtures carry numeric metadata only (per/edits/counts/indices/seeds) —
no lyrics, transcripts or audio content.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from per_cross_arm_analysis import sel_key  # noqa: E402

# Frozen numeric facts of prompt 19 (public-safe: counts and rates only).
PROMPT19 = {
    0: {"per": 0.2260127931769723, "edits": 106, "ref": 469, "phon_len": 458,
        "seed": 831020},
    1: {"per": 0.2260127931769723, "edits": 106, "ref": 469, "phon_len": 472,
        "seed": 831038},
}


def official_key(row: dict) -> tuple:
    per = row["metrics"]["per"]
    rep = per["asr_repeats"][per["selected_asr_repeat"]]
    return (per["per"], per["edits"],
            abs(len(rep["phonemes"]) - per["reference_phonemes"]),
            row["candidate_index"])


def synth_row(d: dict, ci: int, seed: int) -> dict:
    """Build a per_song.jsonl-shaped row from numeric facts only."""
    return {
        "prompt_index": 19, "candidate_index": ci, "seed": seed, "id": f"x_{ci}",
        "metrics": {"per": {
            "per": d["per"], "edits": d["edits"],
            "reference_phonemes": d["ref"], "selected_asr_repeat": 0,
            "asr_repeats": [
                {"phonemes": ["p"] * d["phon_len"]},
                {"phonemes": ["q"] * (d["phon_len"] + 7)},  # decoy repeat
            ],
        }},
    }


def test_prompt19_official_key_selects_r1():
    rows = [synth_row(PROMPT19[ci], ci, PROMPT19[ci]["seed"]) for ci in (0, 1)]
    winner = min(rows, key=official_key)
    assert winner["candidate_index"] == 1, (
        "official key must break the per/edits tie via the phoneme-length "
        "delta (3 < 11) and select r1")


def test_prompt19_old_unfaithful_key_reproduces_the_rc3_divergence():
    """The pre-RC4 sel_key shape (all-repeats sum, asr_repeat final) picks r0.

    Mutation control: if the faithful key ever regresses to this shape, the
    prompt-19 divergence returns. Locked here as a documented negative.
    """
    def old_key(r):
        m = r["metrics"]["per"]
        hyp = (sum(len(x.get("phonemes", [])) for x in m.get("asr_repeats", []))
               or m.get("reference_phonemes", 0))
        return (m.get("per", 1.0), m.get("edits", 10**9),
                abs(hyp - m.get("reference_phonemes", 0)),
                m.get("selected_asr_repeat", 0))

    rows = [synth_row(PROMPT19[ci], ci, PROMPT19[ci]["seed"]) for ci in (0, 1)]
    assert min(rows, key=old_key)["candidate_index"] == 0


def test_sel_key_matches_official_on_random_rows():
    rng = random.Random(20261122)
    for _ in range(500):
        n_rep = rng.randint(1, 4)
        sel = rng.randrange(n_rep)
        lens = [rng.randint(50, 900) for _ in range(n_rep)]
        ref = rng.randint(50, 900)
        row = {
            "prompt_index": rng.randrange(192),
            "candidate_index": rng.randint(0, 1),
            "seed": rng.randint(1, 10**6),
            "metrics": {"per": {
                "per": rng.random(), "edits": rng.randint(0, 400),
                "reference_phonemes": ref, "selected_asr_repeat": sel,
                "asr_repeats": [{"phonemes": ["z"] * n} for n in lens],
            }},
        }
        assert sel_key(row) == official_key(row), row


def test_tie_falls_to_candidate_index_only_on_full_equality():
    """Only a full 4-component equality is a genuine tie; then candidate_index
    (not asr_repeat, not seed) is the deterministic final discriminator."""
    base = {"per": 0.5, "edits": 100, "ref": 400, "phon_len": 396}
    rows = [synth_row(base, ci, 900000 + ci) for ci in (0, 1)]
    assert min(rows, key=official_key)["candidate_index"] == 0


@pytest.mark.skipif(
    not Path("/data/yue2-runs/armB_wsb_full/scores/per_song.jsonl").is_file(),
    reason="frozen Arm B evidence not present on this host")
def test_frozen_armb_selection_192_of_192():
    run = Path("/data/yue2-runs/armB_wsb_full/scores")
    rows = [json.loads(l) for l in (run / "per_song.jsonl").read_text().splitlines()
            if l.strip()]
    official = {(x["prompt_index"], x["candidate_index"], x["seed"])
                for x in json.loads((run / "summary.json").read_text())
                ["selected_candidates"]}
    by_p: dict = {}
    for r in rows:
        by_p.setdefault(r["prompt_index"], []).append(r)
    recomputed = {(p, min(c, key=official_key)["candidate_index"],
                   min(c, key=official_key)["seed"])
                  for p, c in by_p.items()}
    assert recomputed == official, (
        f"selection identity mismatch: {sorted(official ^ recomputed)[:5]}")
