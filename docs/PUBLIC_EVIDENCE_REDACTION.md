# Publication security: WildSongBench text-bearing receipts

The repository was already **public** when this audit found raw WildSongBench
`reference_lyrics`, control prompts, and ASR transcript fields in historical
scoring JSONL, plus embedded per-song data inside the gfx1100 snapshot.

## Current-tree remediation (this PR)

- Remove `evidence/per_song.jsonl` from the current tree rather than publishing
  third-party text or trying to partially transform a 17 MB raw receipt.
- Redact text-bearing fields in three evaluator audit JSONL files and in
  `evidence/gfx1100/scoring_snapshot.json`, retaining numeric metrics,
  identities, sample counts and hashes.
- Add `scripts/public_evidence_guard.py` and CPU regression tests.
- Keep official selected-192 scores and selection audits intact.
- Avoid redistributing generated benchmark lyrics or ASR-derived transcripts.

## IMPORTANT: what this cannot close automatically

**Git commit history still contains previously published blobs**, including
the 17 MB raw per-song file. A normal PR cannot revoke access to prior commits,
forks or caches. Do **not** rewrite Git history without explicit owner approval
and a verified restricted backup of the original receipts. Consult GitHub
Support / the rights holder regarding appropriate historical purge and
downstream copies if necessary.

The original raw receipts are historically available in Git history and need a
separately controlled archival decision. This PR changes no scoring algorithms
or previously reported numeric scores.

## Reviewer verification

```bash
python3 scripts/public_evidence_guard.py
python3 -m pytest -q tests/test_public_evidence.py
```

Re-evaluate third-party redistribution rights before merging or publishing.
