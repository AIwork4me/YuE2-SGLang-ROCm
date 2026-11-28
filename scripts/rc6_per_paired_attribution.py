#!/usr/bin/env python3
"""rc6_per_paired_attribution.py — RC6 A3: complete paired PER attribution.

Two evaluator arms scored the SAME 384 campaign audios:

  T = transformers ROCm ASR arm   (frozen RC5.1 per_full/per_song.jsonl)
  V = vLLM 0.19.1 ROCm ASR arm    (rc5_1_e2_full/rows.jsonl)

Two selections exist:

  S_T = official selection under arm T (05_SELECTED_MANIFEST.json)
  S_V = official selection under arm V (07_CORRECTED_SELECTION_MANIFEST.json)

This tool computes the FULL 2x2 cell matrix on identical audio:

    T(S_T)  V(S_T)      <- evaluator-path effect on the frozen selection
    T(S_V)  V(S_V)      <- selection effect under the corrected evaluator

per cell: micro PER, macro PER, zh/en, S/D/I, reference phonemes, empty
transcripts, token caps; plus prompt-level paired bootstrap CIs and the
selection reconciliation (changed prompts / removed / added / symmetric
difference). Aggregation is pure CPU over frozen receipts; no model runs.

Usage:
  python3 scripts/rc6_per_paired_attribution.py \
      --t-rows <per_full/per_song.jsonl> --v-rows <rc5_1_e2_full/rows.jsonl> \
      --st reports/w7900_rc5/rc5_1/05_SELECTED_MANIFEST.json \
      --sv reports/w7900_rc5/rc5_1/07_CORRECTED_SELECTION_MANIFEST.json \
      --out reports/developer_reference/03_PER_PAIRED_ATTRIBUTION.json \
      --reconciliation-out reports/developer_reference/03_SELECTION_RECONCILIATION.json
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path


def sdi(ref: list, hyp: list) -> dict:
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        ri = ref[i - 1]
        for j in range(1, m + 1):
            c = 0 if ri == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
    s = dele = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            s += ref[i - 1] != hyp[j - 1]
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return {"substitutions": s, "deletions": dele, "insertions": ins}


def load_t(path: Path) -> dict:
    """Transformers arm rows -> {id: {per, edits, reference_phonemes, lang,
    prompt_index, sdi, empty_repeats, capped, selected_repeat}}"""
    out = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        per = r["metrics"]["per"]
        sel = per.get("selected_asr_repeat", 0)
        rep = per["asr_repeats"][sel] if per.get("asr_repeats") else {}
        s = sdi(per["reference_tokens"], rep.get("phonemes", []))
        out[r["id"]] = {
            "per": per["per"], "edits": per["edits"],
            "reference_phonemes": per["reference_phonemes"],
            "lang": r["lang"], "prompt_index": r["prompt_index"],
            "sdi": s,
            "empty_repeats": sum(1 for x in per.get("asr_repeats", [])
                                 if not (x.get("text") or "").strip()),
            "n_repeats": len(per.get("asr_repeats", [])),
            "capped": bool(per.get("truncated_repeats")) or
                      any(x.get("truncated") for x in per.get("asr_repeats", [])),
        }
    return out


def load_v(path: Path) -> dict:
    out = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        s = r.get("sdi") or sdi(r["reference_tokens"],
                                r["asr_repeats"][r["selected_asr_repeat"]]["phonemes"])
        out[r["id"]] = {
            "per": r["per"], "edits": r["edits"],
            "reference_phonemes": r["reference_phonemes"],
            "lang": r["lang"], "prompt_index": r["prompt_index"],
            "sdi": s,
            "empty_repeats": r.get("empty_transcript_repeats",
                                   sum(1 for x in r["asr_repeats"]
                                       if not (x.get("text") or "").strip())),
            "n_repeats": len(r.get("asr_repeats", [])),
            "capped": bool(r.get("first_pass_asr_truncated")) or
                      any(c.get("finish_reason") == "length"
                          for x in r.get("asr_repeats", [])
                          for c in x.get("raw_chunks", [])),
        }
    return out


def cell(rows: dict, ids: list, label: str) -> dict:
    sub = [rows[i] for i in ids]
    e = sum(r["edits"] for r in sub)
    n = sum(r["reference_phonemes"] for r in sub)
    by_lang = {}
    for lang in ("zh", "en"):
        s2 = [r for r in sub if r["lang"] == lang]
        e2 = sum(r["edits"] for r in s2)
        n2 = sum(r["reference_phonemes"] for r in s2)
        by_lang[lang] = {"n_candidates": len(s2), "edits": e2,
                         "reference_phonemes": n2,
                         "micro_per": round(e2 / n2, 8) if n2 else None}
    sdi_t = {k: sum(r["sdi"][k] for r in sub) for k in
             ("substitutions", "deletions", "insertions")}
    return {
        "label": label, "n_candidates": len(sub),
        "micro_per": e / n, "macro_per": sum(r["per"] for r in sub) / len(sub),
        "edits": e, "reference_phonemes": n,
        "by_lang": by_lang, "sdi_totals": sdi_t,
        "empty_transcript_candidates": sum(1 for r in sub if r["empty_repeats"] == r["n_repeats"]),
        "token_cap_candidates": sum(1 for r in sub if r["capped"]),
        "per_max": max(r["per"] for r in sub),
    }


def bootstrap_ci(rows: dict, ids: list, metric: str = "micro", draws: int = 10000,
                 seed: int = 1234) -> list:
    """Prompt-level resampling over the selected ids' prompts."""
    by_prompt = {}
    for i in ids:
        by_prompt.setdefault(rows[i]["prompt_index"], []).append(i)
    prompts = sorted(by_prompt)
    rng = random.Random(seed)
    stats = []
    for _ in range(draws):
        sample = [i for p in (rng.choice(prompts) for _ in range(len(prompts)))
                  for i in by_prompt[p]]
        e = sum(rows[i]["edits"] for i in sample)
        n = sum(rows[i]["reference_phonemes"] for i in sample)
        stats.append(e / n if metric == "micro" else
                     sum(rows[i]["per"] for i in sample) / len(sample))
    stats.sort()
    return [round(stats[int(0.025 * draws)], 6), round(stats[int(0.975 * draws)], 6)]


def prompt_of(cid: str):
    return "_".join(cid.split("_")[:2])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t-rows", type=Path, required=True)
    ap.add_argument("--v-rows", type=Path, required=True)
    ap.add_argument("--st", type=Path, required=True)
    ap.add_argument("--sv", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reconciliation-out", type=Path, required=True)
    ap.add_argument("--draws", type=int, default=10000)
    a = ap.parse_args()

    T, V = load_t(a.t_rows), load_v(a.v_rows)
    st_ids = [c["id"] for c in json.loads(a.st.read_text())["candidates"]]
    sv_ids = [c["id"] for c in json.loads(a.sv.read_text())["candidates"]]

    # coverage sanity
    assert set(T) >= set(st_ids) | set(sv_ids), "transformers arm missing selection ids"
    assert set(V) >= set(st_ids) | set(sv_ids), "vllm arm missing selection ids"
    common_audio = set(T) & set(V)
    assert len(common_audio) == 384, f"expected same 384 audios, got {len(common_audio)}"

    cells = {
        "T(S_T)": cell(T, st_ids, "transformers arm on frozen original selection"),
        "V(S_T)": cell(V, st_ids, "vllm corrected arm on frozen original selection"),
        "T(S_V)": cell(T, sv_ids, "transformers arm on vLLM-corrected selection"),
        "V(S_V)": cell(V, sv_ids, "vllm corrected arm on its own selection"),
    }
    for k in cells:
        cells[k]["micro_per"] = round(cells[k]["micro_per"], 8)
        cells[k]["macro_per"] = round(cells[k]["macro_per"], 8)
        cells[k]["bootstrap_95ci_micro"] = bootstrap_ci(
            {"T": T, "V": V}["T" if k.startswith("T") else "V"],
            st_ids if k.endswith("S_T)") else sv_ids, draws=a.draws)

    decomposition = {
        "evaluator_path_effect_on_frozen_selection": {
            "V(S_T) - T(S_T)": round(cells["V(S_T)"]["micro_per"] - cells["T(S_T)"]["micro_per"], 8)},
        "selection_effect_under_corrected_evaluator": {
            "V(S_V) - V(S_T)": round(cells["V(S_V)"]["micro_per"] - cells["V(S_T)"]["micro_per"], 8)},
        "selection_effect_under_frozen_evaluator": {
            "T(S_V) - T(S_T)": round(cells["T(S_V)"]["micro_per"] - cells["T(S_T)"]["micro_per"], 8)},
        "total_transition": {
            "V(S_V) - T(S_T)": round(cells["V(S_V)"]["micro_per"] - cells["T(S_T)"]["micro_per"], 8)},
        "note": "all cells computed on the SAME 384 audio (audio_sha256 matched at "
                "receipt level; both arms evaluated every candidate)",
    }

    # A3.2 reconciliation with explicit fields
    pst, psv = {prompt_of(i) for i in st_ids}, {prompt_of(i) for i in sv_ids}
    changed = sorted(p for p in pst | psv
                     if {i for i in st_ids if prompt_of(i) == p} != {i for i in sv_ids if prompt_of(i) == p})
    rec = {
        "schema": "yue2-rc6-selection-reconciliation/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "definitions": {
            "changed_prompt_count": "prompts whose selected candidate differs between S_T and S_V",
            "removed_candidate_count": "candidate ids in S_T but not in S_V",
            "added_candidate_count": "candidate ids in S_V but not in S_T",
            "selection_symmetric_difference_count": "|S_T XOR S_V| (candidate-id level)",
        },
        "changed_prompt_count": len(changed),
        "unchanged_prompt_count": len(pst & psv) - len(changed),
        "removed_candidate_count": len(set(st_ids) - set(sv_ids)),
        "added_candidate_count": len(set(sv_ids) - set(st_ids)),
        "selection_symmetric_difference_count": len(set(st_ids) ^ set(sv_ids)),
        "changed_prompts": changed,
        "previous_confusion_resolved": "docs/BENCHMARK_REPRODUCTION.md said '60 changed "
                                       "prompts' while 07_CORRECTED_SELECTION_MANIFEST.json "
                                       "said selection_change_count=120 — BOTH are real "
                                       "numbers under different definitions: 60 changed "
                                       "prompts, 120 candidate-id symmetric difference "
                                       "(60 removed + 60 added). All RC6 reports use the "
                                       "four explicit fields above.",
        "st_manifest": str(a.st), "sv_manifest": str(a.sv),
    }

    out = {
        "schema": "yue2-rc6-per-paired-attribution/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "arms": {
            "T": "transformers ROCm ASR (frozen RC5.1 per_full receipts)",
            "V": "vLLM 0.19.1 ROCm native ASR (E2 corrected arm receipts)",
            "same_audio": "both arms scored the same 384 campaign audios (receipt-level "
                          "audio_sha256 cross-match 384/384, verified in the A2 provenance audit)",
        },
        "cells": cells,
        "decomposition": decomposition,
        "references": {"paper": 0.0844, "author_sgl": 0.081471,
                       "historical_w7900_armB": 0.17762763},
        "frozen_value_crosscheck": {
            "T(S_T)_expected": 0.17769855,
            "T(S_T)_recomputed": cells["T(S_T)"]["micro_per"],
            "V(S_V)_expected": 0.084488,
            "V(S_V)_recomputed": cells["V(S_V)"]["micro_per"],
            "match": (abs(cells["T(S_T)"]["micro_per"] - 0.17769855) < 1e-6 and
                      abs(cells["V(S_V)"]["micro_per"] - 0.084488) < 1e-6),
        },
        "bootstrap": {"method": f"prompt-level resampling, {a.draws} draws, seed 1234, "
                                "95% CI on micro PER per cell"},
    }
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    a.reconciliation_out.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps({k: v["micro_per"] for k, v in cells.items()}, indent=1))
    print(json.dumps({k: rec[k] for k in ("changed_prompt_count", "removed_candidate_count",
                                          "added_candidate_count",
                                          "selection_symmetric_difference_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
