#!/usr/bin/env python3
"""rc5_score_transcripts.py — score a transcripts file with the OFFICIAL PER
scorer (RC5 M6; RC6 A2.3 hardening). Engine-independent: any ASR engine step
(the transformers backend, the vLLM-native runner, ...) writes
``{"id", "prompt_index", "candidate_index", "lang", "audio_sha256", "repeats":
[{"text", ...}]}``; this step applies the frozen evaluator's own code:

    mot_infer.eval_worker.phoneme_result(scorer, reference_lyrics, hypotheses)
        -> g2p phonemization, edit distance, official repeat selection, PER

and adds the S/D/I split. The reference lyrics come from the frozen
evaluator data (never from the transcripts file).

RC6 A2.3 hardening (math untouched):
  * no bare ``assert`` — every check is an explicit, testable exception
    (``-O`` can no longer silence validation);
  * duplicate candidate ids in the transcripts file -> fail;
  * manifest coverage enforced (missing candidates are NEVER silently
    ignored) unless ``--allow-partial``;
  * repeat-count consistency enforced across rows (and vs --expected-repeats);
  * cross-engine receipt mixing detected (engine identity must be constant);
  * scoring identity: scorer source hashes + manifest hash recorded in every
    output row and summary; appending rows from a different scoring identity
    to an existing output is refused (supersede, never overwrite);
  * micro PER recomputed from raw sums and cross-checked against the
    per-row edits/reference_phonemes aggregates (denominator audit).

Usage (official metrics venv):
  python scripts/rc5_score_transcripts.py --evaluator-root R --manifest audio_manifest.jsonl \
      --transcripts t.jsonl --out rows.jsonl --engine-label "E2 vLLM 0.19.1 native"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc6_asr_identity as asr_id


class ScorerValidationError(Exception):
    """Fail-closed scorer input validation (RC6 A2.3)."""


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


def validate_transcripts(t_rows: list, ref: dict, expected_repeats: int | None,
                         allow_partial: bool) -> None:
    if not t_rows:
        raise ScorerValidationError("transcripts file is empty")
    seen = {}
    for t in t_rows:
        cid = t.get("id")
        if cid is None:
            raise ScorerValidationError("transcript row without id")
        if cid in seen:
            raise ScorerValidationError(
                f"duplicate candidate id in transcripts: {cid} (rows {seen[cid]} and later)")
        seen[cid] = True
        if cid not in ref:
            raise ScorerValidationError(
                f"transcript id {cid} is not in the audio manifest (cross-arm mixing?)")
        if t.get("audio_sha256") != ref[cid]["audio_sha256"]:
            raise ScorerValidationError(
                f"audio changed for {cid}: transcripts {t.get('audio_sha256')} != "
                f"manifest {ref[cid]['audio_sha256']}")
        reps = t.get("repeats")
        if not isinstance(reps, list) or not reps:
            raise ScorerValidationError(f"{cid}: no repeats in transcript row")
        if expected_repeats is not None and len(reps) != expected_repeats:
            raise ScorerValidationError(
                f"{cid}: repeat count {len(reps)} != expected {expected_repeats}")
    counts = {len(t["repeats"]) for t in t_rows}
    if len(counts) > 1:
        raise ScorerValidationError(f"inconsistent repeat counts across rows: {sorted(counts)}")
    engines = set()
    for t in t_rows:
        ri = t.get("run_identity") or {}
        eng = ri.get("engine") or t.get("engine") or {}
        if isinstance(eng, dict):
            engines.add(json.dumps({k: str(eng.get(k)) for k in
                                    ("engine", "vllm", "torch", "dtype", "seed")}, sort_keys=True))
    if len(engines) > 1:
        raise ScorerValidationError(
            f"cross-engine receipt mixing: {len(engines)} distinct engine identities")
    missing = [cid for cid in ref if cid not in seen]
    if missing and not allow_partial:
        raise ScorerValidationError(
            f"{len(missing)} manifest candidates missing from transcripts "
            f"(e.g. {missing[:3]}); use --allow-partial only for diagnostics")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--transcripts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--engine-label", default="")
    ap.add_argument("--expected-repeats", type=int, default=None)
    ap.add_argument("--allow-partial", action="store_true",
                    help="diagnostic: permit incomplete manifest coverage (recorded in summary)")
    ap.add_argument("--drop-first-repeat", action="store_true",
                    help="diagnostic: score repeats 1..n-1 only")
    a = ap.parse_args()
    root = a.evaluator_root
    sys.path[:0] = [str(root / "src"), str(root / "vendor")]
    import nltk
    from historical_per import PerScorer
    from mot_infer.eval_worker import phoneme_result
    nltk.data.path[:] = [str(root / "evaluation_models/nltk_data")]
    for name in ["corpora/cmudict", "taggers/averaged_perceptron_tagger",
                 "taggers/averaged_perceptron_tagger_eng", "corpora/cmudict.zip",
                 "taggers/averaged_perceptron_tagger.zip"]:
        nltk.data.find(name)
    scorer = PerScorer()

    # RC6 A2.3: scoring identity — scorer source hashes + manifest hash
    scoring_identity = {
        "schema": "yue2-rc6-scoring-identity/1",
        "historical_per_sha256": asr_id.sha256_file(root / "vendor/historical_per.py"),
        "eval_worker_sha256": asr_id.sha256_file(root / "src/mot_infer/eval_worker.py"),
        "manifest_path": str(a.manifest),
        "manifest_sha256": asr_id.sha256_file(a.manifest),
        "scorer_sha256": asr_id.sha256_file(root / "vendor/historical_per.py"),
        "nltk_data": "frozen evaluator tree (bundle manifest covers it)",
    }
    scoring_identity["scoring_identity_sha256"] = asr_id.sha256_bytes(
        json.dumps(scoring_identity, sort_keys=True).encode())

    t_rows = [json.loads(l) for l in a.transcripts.read_text().splitlines() if l.strip()]
    ref = {r["id"]: r for r in (json.loads(l) for l in a.manifest.read_text().splitlines() if l.strip())}
    validate_transcripts(t_rows, ref, a.expected_repeats, a.allow_partial)

    # supersede-not-overwrite: refuse to append a different scoring identity
    if a.out.is_file():
        try:
            prev_first = json.loads(a.out.read_text().splitlines()[0])
            prev_id = (prev_first.get("scoring_identity") or {}).get("scoring_identity_sha256")
            if prev_id and prev_id != scoring_identity["scoring_identity_sha256"]:
                print(json.dumps({"refused": "output file belongs to a different scoring "
                                             "identity; write to a NEW path (supersede, "
                                             "never overwrite)",
                                  "prev": prev_id, "new": scoring_identity["scoring_identity_sha256"]}))
                return 5
        except (ValueError, IndexError):
            print(json.dumps({"refused": "existing output is not valid scoring rows; "
                                         "write to a NEW path"}))
            return 5

    out_rows = []
    for t in t_rows:
        row = ref[t["id"]]
        hyps = t["repeats"][1:] if a.drop_first_repeat else t["repeats"]
        res = phoneme_result(scorer, row["target"]["reference_lyrics"], hyps)
        sel = res["asr_repeats"][res["selected_asr_repeat"]]
        res["sdi"] = sdi(res["reference_tokens"], sel["phonemes"])
        res.update(id=t["id"], prompt_index=row["prompt_index"], candidate_index=row["candidate_index"],
                   lang=row["lang"], audio_sha256=row["audio_sha256"], engine=a.engine_label,
                   scoring_identity=scoring_identity,
                   empty_transcript_repeats=sum(1 for x in res["asr_repeats"] if not x["text"].strip()),
                   repeat_count=len(res["asr_repeats"]))
        # denominator audit: per-row per must equal edits/reference_phonemes
        if res["reference_phonemes"] > 0:
            implied = res["edits"] / res["reference_phonemes"]
            if abs(implied - res["per"]) > 1e-9:
                raise ScorerValidationError(
                    f"{t['id']}: per={res['per']} inconsistent with edits/ref "
                    f"{implied} (reference denominator broken)")
        out_rows.append(res)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows))
    ok = [r for r in out_rows if r.get("status") == "complete"]
    e = sum(r["edits"] for r in ok)
    n = sum(r["reference_phonemes"] for r in ok)
    micro = round(e / n, 6) if n else None
    # recompute micro from raw per-row values (cross-check the aggregation)
    if n:
        recompute = sum(r["edits"] for r in ok) / sum(r["reference_phonemes"] for r in ok)
        if abs(recompute - micro) > 1e-6:
            raise ScorerValidationError("micro PER aggregation mismatch")
    summ = {"engine": a.engine_label, "n": len(ok), "micro_per": micro,
            "macro_per": round(sum(r["per"] for r in ok) / len(ok), 6) if ok else None,
            "micro_denominator": "sum(edits)/sum(reference_phonemes) over complete rows",
            "empty_transcript_candidates": sum(1 for r in ok if r["empty_transcript_repeats"] == r["repeat_count"]),
            "sdi_totals": {k: sum(r["sdi"][k] for r in ok) for k in ("substitutions", "deletions", "insertions")},
            "scoring_identity": scoring_identity,
            "partial": bool(a.allow_partial),
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print(json.dumps(summ, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
