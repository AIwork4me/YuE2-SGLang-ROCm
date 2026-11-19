#!/usr/bin/env python3
"""sample_classification.py — evidence-based sample classification (C2 P1).

Scientific semantics:
  * PER≈1.0 does NOT imply an empty ASR transcript (edit-distance error can
    reach or exceed 1.0 on non-empty output). Empty is a property of the
    TRANSCRIPT, knowable only from transcript evidence.
  * Labels (ASR_CAPPED / HIGH_PER / LANG_*) may legitimately cross; empty
    state is tracked separately and is never inferred from PER.
  * Where public receipts redacted the ASR text, empty state is
    EMPTY_UNKNOWN — never silently False, never guessed.

Public API:
  empty_state(row) -> (state, evidence_receipt)
  labels(row)      -> cross-capable label list
  assert_conservation(rows, selected_ids) -> conservation receipt (fail-closed)
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter

EMPTY_CONFIRMED = "EMPTY_CONFIRMED"
NONEMPTY_CONFIRMED = "NONEMPTY_CONFIRMED"
EMPTY_UNKNOWN = "EMPTY_UNKNOWN"


def _per_metrics(row: dict) -> dict:
    m = row.get("metrics", {}).get("per", {})
    if not isinstance(m, dict):
        raise ValueError(f"{row.get('id')}: per metrics missing/not an object")
    return m


def _selected_transcript_text(row: dict) -> str | None:
    """Return the selected ASR repeat's transcript text, or None if the
    receipt does not carry transcript text (redacted / numeric-only)."""
    m = _per_metrics(row)
    repeats = m.get("asr_repeats")
    sel = m.get("selected_asr_repeat")
    if not isinstance(repeats, list) or not isinstance(sel, int):
        return None
    if not (0 <= sel < len(repeats)):
        raise ValueError(f"{row.get('id')}: selected_asr_repeat out of range")
    entry = repeats[sel]
    if not isinstance(entry, dict):
        return None
    text = entry.get("text")
    return text if isinstance(text, str) else None


def empty_state(row: dict, source_sha: str | None = None) -> tuple[str, dict]:
    """(state, evidence). EMPTY_CONFIRMED requires DIRECT transcript evidence:
    the selected ASR repeat's text, present and empty. Evidence receipts carry
    a sha256 of the exact evaluated string so a restricted original can be
    cross-checked later without republishing it."""
    m = _per_metrics(row)
    text = _selected_transcript_text(row)
    if text is None:
        return EMPTY_UNKNOWN, {
            "basis": "selected ASR transcript not present in receipt",
            "per": m.get("per"),
            "source_sha256": source_sha,
        }
    digest = hashlib.sha256(text.encode()).hexdigest()
    return (
        (EMPTY_CONFIRMED if not text.strip() else NONEMPTY_CONFIRMED),
        {"basis": "selected ASR transcript text",
         "transcript_sha256": digest,
         "transcript_len": len(text),
         "selected_asr_repeat": m.get("selected_asr_repeat"),
         "source_sha256": source_sha,
         "per": m.get("per")},
    )


def labels(row: dict) -> list[str]:
    """Cross-capable labels (NOT mutually exclusive, by design)."""
    m = _per_metrics(row)
    out = []
    if m.get("selected_asr_truncated") is True:
        out.append("ASR_CAPPED")
    per = m.get("per")
    if isinstance(per, (int, float)) and math.isfinite(per) and per > 0.30:
        out.append("HIGH_PER")
    lang = row.get("lang")
    if lang == "zh":
        out.append("LANG_ZH")
    elif lang == "en":
        out.append("LANG_EN")
    elif lang is None or lang == "":
        out.append("LANG_UNKNOWN")
    else:
        out.append(f"LANG_{lang}")
    return out


def assert_conservation(rows: list[dict], selected: list[dict]) -> dict:
    """Fail-closed 384/192/2-per-prompt conservation receipt. Label sets never
    change these totals (verified by the caller comparing before/after)."""
    if len(rows) != 384:
        raise ValueError(f"expected 384 candidate receipts, got {len(rows)}")
    ids = [r.get("id") for r in rows]
    if len(set(ids)) != 384:
        dupes = [k for k, v in Counter(ids).items() if v > 1]
        raise ValueError(f"duplicate candidate ids: {dupes[:3]}")
    per_prompt = Counter()
    for r in rows:
        per_prompt[r.get("prompt_index")] += 1
    if set(per_prompt) != set(range(192)) or any(
            v != 2 for v in per_prompt.values()):
        raise ValueError("frozen 192-prompt x 2-candidate shape violated")
    if len(selected) != 192:
        raise ValueError(f"official selection must be 192, got {len(selected)}")
    sel_keys = [(r["prompt_index"], r["candidate_index"]) for r in selected]
    if len(set(sel_keys)) != 192:
        raise ValueError("selection contains duplicate coordinates")
    sel_prompts = Counter(i for i, _ in sel_keys)
    if set(sel_prompts) != set(range(192)) or any(
            v != 1 for v in sel_prompts.values()):
        raise ValueError("selection must pick exactly one candidate per prompt")
    return {"candidates": 384, "prompts": 192, "selected": 192,
            "unselected": 192, "shape": "192x2, one selected per prompt"}
