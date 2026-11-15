#!/usr/bin/env python3
"""PER tail analysis with correct selected-192 denominator and provenance.

Publication-grade selection MUST use the frozen scorer's exact
`scores/summary.json::selected_candidates` list. Diagnostic minimum-PER
selection is explicitly labelled non-authoritative. Never infer an empty
transcript from PER==1.0; missing transcript text means UNKNOWN.
No GPU is necessary; source audio remains in restricted storage.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def per_fields(row: dict) -> dict:
    m = row.get("metrics", {}).get("per", {})
    per = m.get("per")
    edits = m.get("edits")
    phonemes = m.get("reference_phonemes")
    if not isinstance(per, (float, int)) or not math.isfinite(per) or per < 0:
        raise ValueError("Missing or invalid per metric")
    if not isinstance(edits, int) or edits < 0:
        raise ValueError("Missing or invalid edit count")
    if not isinstance(phonemes, int) or phonemes <= 0:
        raise ValueError("Missing or invalid reference phoneme count")
    repeats = m.get("asr_repeats")
    selected_repeat = m.get("selected_asr_repeat")
    empty = None  # UNKNOWN if transcript is redacted/not retained
    if isinstance(repeats, list) and isinstance(selected_repeat, int):
        if 0 <= selected_repeat < len(repeats):
            transcript = repeats[selected_repeat].get("text")
            if isinstance(transcript, str):
                empty = not bool(transcript.strip())
    return {
        "per": float(per),
        "edits": edits,
        "phonemes": phonemes,
        "empty": empty,
        "asr_capped": bool(m.get("selected_asr_truncated")),
        "lang": row.get("lang"),
    }


def choose_rows(rows: list[dict], summary: dict | None = None):
    if len(rows) != 384:
        raise ValueError(f"Expected exactly 384 candidate receipts; got {len(rows)}")
    keyed = {}
    by_prompt = {}
    for row in rows:
        pi = row.get("prompt_index")
        ci = row.get("candidate_index")
        if not isinstance(pi, int) or not 0 <= pi < 192 or ci not in (0, 1):
            raise ValueError("Invalid candidate coordinates")
        key = (pi, ci)
        if key in keyed:
            raise ValueError(f"Duplicate candidate: {key}")
        per_fields(row)
        keyed[key] = row
        by_prompt.setdefault(pi, []).append(row)
    if set(by_prompt) != set(range(192)) or any(
        {x["candidate_index"] for x in pair} != {0, 1}
        for pair in by_prompt.values()
    ):
        raise ValueError("Missing candidate or prompt")
    if summary is not None:
        selection = summary.get("selected_candidates")
        if not isinstance(selection, list) or len(selection) != 192:
            raise ValueError("Official selection must contain exactly 192 candidates")
        selected, seen = [], set()
        for item in selection:
            key = (item["prompt_index"], item["candidate_index"])
            if key[0] in seen or key not in keyed:
                raise ValueError("Official selection has duplicate/unknown coordinates")
            row = keyed[key]
            for id_field in ("seed", "audio_sha256"):
                if item.get(id_field) is not None and row.get(id_field) is not None:
                    if item[id_field] != row[id_field]:
                        raise ValueError(f"Official {id_field} mismatches candidate identity")
            seen.add(key[0])
            selected.append(row)
        if seen != set(range(192)):
            raise ValueError("Official selection incomplete")
        provenance = "OFFICIAL_SELECTED_CANDIDATES_VERIFIED"
    else:
        selected = []
        for pi in range(192):
            left, right = by_prompt[pi]
            a, b = per_fields(left)["per"], per_fields(right)["per"]
            if a == b:
                raise ValueError(
                    "Candidate PER tie without official selection: provide --selection-summary"
                )
            selected.append(left if a < b else right)
        provenance = "DIAGNOSTIC_MIN_PER_ONLY_NOT_OFFICIAL"
    selected_keys = {(x["prompt_index"], x["candidate_index"]) for x in selected}
    other = [r for r in rows if (r["prompt_index"], r["candidate_index"]) not in selected_keys]
    if len(other) != 192 or len(selected) != 192:
        raise ValueError("Selection partition is not 192/192")
    return selected, other, provenance


def stats(rows: list[dict]) -> dict:
    f = [per_fields(r) for r in rows]
    edits = sum(x["edits"] for x in f)
    n = sum(x["phonemes"] for x in f)
    return {"candidates": len(rows), "edits": edits, "phonemes": n,
            "micro_per": edits / n if n else None}


def bootstrap_ci(rows: list[dict], n: int = 2000, seed: int = 42):
    if not rows:
        return [None, None]
    fields = [per_fields(r) for r in rows]
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        resample = [fields[rng.randrange(len(fields))] for _ in rows]
        total = sum(x["phonemes"] for x in resample)
        vals.append(sum(x["edits"] for x in resample) / total)
    vals.sort()
    return [vals[int(.025 * (n - 1))], vals[int(.975 * (n - 1))]]


def analyze(path: Path, selection_summary: Path | None = None, bootstrap: int = 2000) -> dict:
    rows = load_rows(path)
    summary = json.loads(selection_summary.read_text()) if selection_summary else None
    selected, unselected, provenance = choose_rows(rows, summary)
    groups = {
        "selected_192": selected,
        "unselected_192": unselected,
        "all_384": rows,
    }
    out = {
        "schema": "per-tail-analysis/v2",
        "input": str(path),
        "selection_provenance": provenance,
        "publication_grade_selection": summary is not None,
        "populations": {k: stats(v) for k, v in groups.items()},
        "selected_bootstrap_ci95": bootstrap_ci(selected, n=bootstrap),
    }
    sel_stats = out["populations"]["selected_192"]
    e_total, p_total = sel_stats["edits"], sel_stats["phonemes"]
    capped = {}
    # These six categories are DISJOINT and cover all selected songs.
    for cap in (False, True):
        for empty in (False, True, None):
            name = f"capped={cap},empty={empty}"
            subset = [
                row for row in selected
                if per_fields(row)["asr_capped"] is cap and per_fields(row)["empty"] is empty
            ]
            cur = stats(subset)
            cur["edit_share_selected"] = cur["edits"] / e_total if e_total else None
            cur["per_point_contribution"] = cur["edits"] / p_total if p_total else None
            capped[name] = cur
    if sum(v["candidates"] for v in capped.values()) != 192:
        raise AssertionError("Selected cross-tab does not partition 192 songs")
    if sum(v["edits"] for v in capped.values()) != e_total:
        raise AssertionError("Selected edit counts do not sum")
    if sum(v["phonemes"] for v in capped.values()) != p_total:
        raise AssertionError("Selected phoneme counts do not sum")
    out["selected_disjoint_capped_x_empty"] = capped
    out["selected_per_over_0_30"] = sum(per_fields(x)["per"] > .30 for x in selected)
    out["selected_per_equal_1"] = sum(per_fields(x)["per"] == 1.0 for x in selected)
    out["selected_language"] = {
        lang: stats([r for r in selected if r.get("lang") == lang])
        for lang in sorted({r.get("lang") for r in selected if r.get("lang")})
    }
    out["warning"] = (
        "This decomposes the current selected-192 PER, NOT the causal "
        "difference from official 8.44%; evaluator/backend controls required. "
        "Empty transcript is UNKNOWN when ASR texts are redacted."
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("per_song_jsonl", type=Path)
    ap.add_argument("--selection-summary", type=Path, default=None,
                    help="REQUIRED for publication-grade official best-of-two selection")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.bootstrap <= 0:
        ap.error("--bootstrap must be positive")
    result = analyze(args.per_song_jsonl, args.selection_summary, args.bootstrap)
    content = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(content)
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
