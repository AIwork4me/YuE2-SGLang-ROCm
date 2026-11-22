# RC4 M4.6 — Public Evidence Audit

Date: 2026-11-22. Working tree: `mission/w7900-rc4-repro-reliability`.

## Guards executed (this session, on the RC4 tree)

| Guard | Command | Result |
|---|---|---|
| Tier-1 structured-evidence gate | `python3 scripts/public_evidence_guard.py` | **PASS** (no blocked text-bearing fields; historical git objects out of scope by design) |
| Tier-2 real-dataset scan | `python3 scripts/evidence_lyrics_detector.py --ref HEAD` | **PASS** (408 tracked files, tier1+tier2, 1813 ground-truth windows from frozen manifest) |

## Publication hygiene rules honored in this mission

- Frozen campaign audio/lyrics never leave `/data`; only numeric aggregates,
  redacted metadata, counts and hashes enter `reports/w7900_rc4/`.
- The RC4 truncation/tie reviews carry per/edits/phoneme-count/seed fields
  only — no lyrics, transcripts, or phoneme text.
- No new binary media committed; `git ls-files` stays text-only.
- Personal/path information in reports is limited to reproducible host
  identifiers already public in prior reports.
- Historical Git-object cleanup remains owner/legal-gated (unchanged stance
  from RC3); no history rewrite performed or proposed by this mission.

## New RC4 artifacts published by this branch (inventoried)

- `reports/w7900_rc4/00_*` — environment/git/plan (sanitized, no secrets)
- `reports/w7900_rc4/01_*` — fresh-clone receipts (command → receipt JSONL,
  dependency provenance, negative controls, verdict)
- `reports/w7900_rc4/02_*` — runtime RCA, reliability/memory CSVs, verdict
- `reports/w7900_rc4/03_*` — performance raw/summary/verdicts
- `reports/w7900_rc4/04_*` — tie/truncation/provenance/public-evidence audits
- `reports/w7900_rc4/05_*` + `FINAL_REPORT_ZH.md` — review, CI/GPU regression,
  release gates, handoff
- `scripts/rc4_*.py` — test tooling (no dataset content)
- `tests/test_selection_tie_semantics.py` — numeric-only fixtures

## Residual risks (unchanged, owner-gated)

- Historical Git objects predating the redaction guards: owner/legal decision
  (options documented in RC3 02_SECURITY_LICENSE_REVIEW carry-over).
- No YuE2-author or AMD approval implied anywhere; G9/G10 remain NOT_PRESENT.
