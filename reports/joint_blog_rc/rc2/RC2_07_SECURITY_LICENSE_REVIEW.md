# RC2_07b — Security, licensing & provenance review (RC2 session)

**Scope:** PR #15 content + RC2 branch changes (`mission/joint-blog-rc2` @
`16cd217`). CPU-only. No licensed raw data left `/data` except the validated
kit staging under `/data/yue2/tmp/rc2_kit_validation/` (workspace scratch,
same host, private).

## Checks executed this session

| # | Check | Result |
|---|---|---|
| 1 | `public_evidence_guard.py` on the RC2 tree | **PASS** (tracked structured evidence: no blocked fields) |
| 2 | `compileall` scripts+supervisor | PASS |
| 3 | `bash -n` all scripts | PASS |
| 4 | New public artifacts content review (RC2_03 kit, manifests, analyses) | hashes/ids/aggregates only — no lyrics, transcripts, or audio |
| 5 | Bundle manifest (602 KB, 384×11 file hashes) | verified: JSON contains only ids/indices/seeds/sha256/bytes |
| 6 | Length-effect analysis outputs | aggregates + CIs only |
| 7 | Author message draft | no restricted data; honest statuses |
| 8 | Test-suite changes | no fixtures with licensed text; stub lyrics are original (SMOKE_LYRICS) |

## Re-verified from M6 (unchanged inputs)

- Tier-1 + tier-2 (1813 real lyric windows, `--require-ground-truth`) scans
  on the integrated tree: PASS (M6, 2026-11-19).
- Numeric receipt integrity semantics + 31 redaction tests: green in the
  RC2 suite run (373/0).
- Provenance chain (`verify_provenance.py`, Arm A): PASS, 0 violations.

## Open items (owner decisions, honestly tracked)

| Item | Status | Note |
|---|---|---|
| Historical Git objects (pre-#7) | **OPEN — legal/security decision** | working-tree gates protect every future clone's checkout; server-side history still contains old objects. Options (a) accept+document, (b) authorized rewrite, (c) GitHub-assisted purge. Not auto-labeled solved. |
| Private transfer authorization (16.3 GiB/arm) | PENDING (EXT-5) | bundles contain licensed-lyric performances; private channel mandatory |
| Upstream submissions | NONE made | all gated |

## Verdict

**PASS for the RC2 session's own artifacts**, with the historical-objects
decision and transfer authorization explicitly carried as owner items.
