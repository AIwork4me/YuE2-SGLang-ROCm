# SECURITY FINAL — Fresh Image (Phase P8)

Written: 2026-11-15 · Executor: fresh-image session 1
Scope: audit of THIS repository's public content (current HEAD + git history) for
unauthorized or unsafe material. Historical audits: `reports/publication/09_SECURITY_AUDIT.md`.

## 1. LQ-1 — WildSongBench reference lyrics in git evidence (CONFIRMED, remediation prepared)

### Findings (verified on this fresh clone, not from memory)

Lyrics-bearing files at current HEAD (`mission/...` branch base `fdfc0ac`):

| File | Rows with lyrics | Content |
|---|---|---|
| `evidence/per_song.jsonl` | 384 | full WSB reference lyrics (`target.*`, `metrics.per.reference_lyrics`, phoneme `reference_tokens`, ASR `asr_repeats[].text` which substantially reproduce the lyrics) |
| `evidence/publication/armA_pilot/per_song.jsonl` | 2 | same shape |
| `evidence/evaluator_audit/per_run{A,B,C}_*.jsonl` | 2/10/10 | same shape |
| `evidence/gfx1100/scoring_snapshot.json` | 4 | embedded per-song rows |

Git history: 150 commits total; the lyrics files were introduced in a small
number of commits (e.g. `1f23c8e`, `ebb6995`, `9e489c6`) and are reachable from
the public remote today.

### Remediation state on this branch

1. **Redaction tooling** `scripts/redact_evidence.py` (committed): path-aware,
   round-trip-verified; replaces lyric text/phonemes/transcripts with
   `sha256:12` digests — scientific values, identities, hashes and counts are
   preserved byte-for-byte.
2. **Redacted siblings** for every lyrics-bearing file at HEAD (committed):
   `*.redacted.jsonl/json` — zero lyric-string occurrences (grep-verified).
3. **Originals untouched** — swapping originals out of the public tree, and any
   git history rewrite, requires the owner's decision (mission rule P8;
   do not rewrite public history without approval).

### Decision required from owner (blocking blog publication, not campaigns)

- **Option A (recommended)**: replace originals with redacted copies at HEAD +
  request WildSongBench authors' permission for the restricted full receipts +
  keep originals in restricted storage. Public git history still contains the
  lyrics; note in README + take-down contact.
- **Option B**: additionally rewrite public history (destructive: breaks all
  cloned SHAs and the pushed evidence chain; requires coordination with every
  fork/clone holder).
- **Option C**: obtain written permission from the dataset authors to keep
  lyric excerpts under research-quotation terms; document the permission.

## 2. Other checks (current HEAD, fresh clone)

| Check | Result |
|---|---|
| Credentials / tokens / keys in git | none found (historical audit 09 + spot re-check of env-var patterns; proxy credentials are injected at runtime, never committed) |
| Internal hostnames / paths | historical machine paths (`/home/amd/...`) appear in patch headers (documentation of provenance, no credential value) |
| Dataset audio redistribution | none in git (audio lives only on the machine, `/data/yue2-runs`) |
| Model weights in git | none (weights fetched from HF at pinned revisions, sha256-verified) |
| Demo audio licensing | demo lyrics used by fresh-image acceptance are original text written for this repo; historical demo audio questions → `09_LICENSE_AND_ATTRIBUTION.md` |
|unsafe URLs / HTTP downgrades | none; all fetchers HTTPS with retry |

## 3. Fresh-image evidence policy going forward

- Campaign/scoring receipts produced on this image will be committed ONLY in
  lyric-redacted form (`scripts/redact_evidence.py` is part of the evidence
  pipeline; `summarize_campaign.py` outputs carry no lyric text).
- Raw per-song JSONL with lyrics stays on `/data` (machine-local, restricted);
  if the image is reclaimed, those files die with it — audited summaries +
  hashes in git are the durable record.

## 4. Verdict

- **Code/infra security: PASS** (no secrets, no unsafe transport, no weights in git).
- **Publication security: BLOCKED on the owner's LQ-1 decision** (Option A/B/C
  above). This mirrors historical gate G13 and is unchanged by the fresh image.


## 2026-11-15 CPU-only corrective proposal (Draft PR #10)

A separate Draft PR proposes a *current-tree* change: remove the 17MB raw
`evidence/per_song.jsonl` and the duplicate incomplete `*.redacted*`
exports, replace five remaining text-bearing JSON/JSONL receipts with
numeric-only forms (retained numeric leaves compared exactly), and add a
GitHub CI public-evidence gate plus regression tests. The older 2.6MB Arm B
`per_song_redacted.jsonl` also contained unsafe fields and is excluded
from the proposed public tree; the original candidate manifest, aggregate
scores and hashes remain. A rights-cleared, numeric-only 384-row public
replacement requires re-exporting from restricted originals, not copying
uninspected redacted files. No historical scores were changed.

**Historical Git objects still remain publicly accessible.** This Draft PR
has not been merged into the already-public main/mission branch. Consult the
owner and rights holders before any history rewrite or public release.

The script `scripts/redact_evidence.py` now strips text fields and
phoneme arrays regardless of character length; previous length>50 hashing
was inadequate for short lyrics and phoneme strings. Use the CI guard for
all future exports. The W7900 run /data directories were not accessed.
