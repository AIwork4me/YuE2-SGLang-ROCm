#!/usr/bin/env python3
"""rc5_score_transcripts.py — score a transcripts file with the OFFICIAL PER
scorer (RC5 M6). Engine-independent: any ASR engine step (the transformers
backend, the vLLM-native runner, ...) writes
``{"id", "prompt_index", "candidate_index", "lang", "audio_sha256", "repeats":
[{"text", ...}]}``; this step applies the frozen evaluator's own code:

    mot_infer.eval_worker.phoneme_result(scorer, reference_lyrics, hypotheses)
        -> g2p phonemization, edit distance, official repeat selection, PER

and adds the S/D/I split. The reference lyrics come from the frozen
evaluator data (never from the transcripts file).

Usage (official metrics venv):
  python scripts/rc5_score_transcripts.py --evaluator-root R --manifest audio_manifest.jsonl \
      --transcripts t.jsonl --out rows.jsonl --engine-label "E2 vLLM 0.19.1 native"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--transcripts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--engine-label", default="")
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
    ref = {r["id"]: r for r in (json.loads(l) for l in a.manifest.read_text().splitlines() if l.strip())}
    out_rows = []
    for line in a.transcripts.read_text().splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        row = ref[t["id"]]
        assert t["audio_sha256"] == row["audio_sha256"], f"audio changed for {t['id']}"
        hyps = t["repeats"][1:] if a.drop_first_repeat else t["repeats"]
        res = phoneme_result(scorer, row["target"]["reference_lyrics"], hyps)
        sel = res["asr_repeats"][res["selected_asr_repeat"]]
        res["sdi"] = sdi(res["reference_tokens"], sel["phonemes"])
        res.update(id=t["id"], prompt_index=row["prompt_index"], candidate_index=row["candidate_index"],
                   lang=row["lang"], audio_sha256=row["audio_sha256"], engine=a.engine_label,
                   empty_transcript_repeats=sum(1 for x in res["asr_repeats"] if not x["text"].strip()),
                   repeat_count=len(res["asr_repeats"]))
        out_rows.append(res)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows))
    ok = [r for r in out_rows if r.get("status") == "complete"]
    e = sum(r["edits"] for r in ok)
    n = sum(r["reference_phonemes"] for r in ok)
    summ = {"engine": a.engine_label, "n": len(ok), "micro_per": round(e / n, 6) if n else None,
            "macro_per": round(sum(r["per"] for r in ok) / len(ok), 6) if ok else None,
            "empty_transcript_candidates": sum(1 for r in ok if r["empty_transcript_repeats"] == r["repeat_count"]),
            "sdi_totals": {k: sum(r["sdi"][k] for r in ok) for k in ("substitutions", "deletions", "insertions")}}
    print(json.dumps(summ, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
