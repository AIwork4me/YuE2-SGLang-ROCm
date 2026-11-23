# RC4.1 M4 — README & docs review

Reviewed: README.md, docs/QUICKSTART.md, docs/EVIDENCE_INDEX.md,
docs/KNOWN_LIMITATIONS.md, docs/COMPATIBILITY_MATRIX.md (exists? yes under
docs/), docs/RESULTS.md, docs/BENCHMARK_REPRODUCTION.md.

## Fixed this mission (README.md)

1. Status block updated to RC4.1: fail-loud GPU identity, real readiness,
   lifecycle wrapper, bounded input contract, audited evidence
   consistency (791 rows) — with links to reports/w7900_rc4_1/.
2. "Native PyTorch full-run results remain pending" — STALE since RC3
   (Arm A 384/384 FULL + official scoring exist). Replaced with the
   actual Arm A results summary.
3. Performance table: RC2-era figures (245.8 s median, ~41 GiB, ~7 min)
   replaced by the RC4 frozen-campaign numbers (P50 275.3/706.4 s;
   fresh-warm 248.3/630.4 s; VRAM 47.1 GiB pilot / 51.5 decimal GB
   campaign) with explicit n, sources and the audit-tool pointer;
   historical figures retained in docs/RESULTS.md (labeled historical).
4. Quick start: added the three verification commands a developer
   actually needs (gpu_identity verify, run_with_server session,
   server_readiness check) — directly answering "how do I verify this is
   really the GPU?" and "how do I stop safely?".

## Reviewed, no change needed (current and accurate)

- Licensing block (CC BY-NC 4.0; no weights/lyrics redistribution) —
  accurate and kept.
- Upstream status (SGLang PR #42106 unmerged; Q3O NOT TESTED 80 GB) —
  accurate; Q3O remains NOT_TESTED on 48 GB.
- docs/KNOWN_LIMITATIONS.md — RC4 additions current; RC4.1 appends
  nothing new limiting (see below for the one candidate).
- docs/QUICKSTART.md — RC4-hardened (TMPDIR/HF env/venv/interpreter
  gaps already fixed with receipts). HF env override bit us AGAIN this
  mission on the native pilot (host env HF_HUB_CACHE pointed at the full
  /workspace; fixed in the session script, not a doc gap: QUICKSTART
  already documents the override).
- docs/EVIDENCE_INDEX.md — RC4 current-generation tables already
  run_id-keyed; RC4.1 adds its own report dir (indexed in
  04_PUBLIC_EVIDENCE_INDEX.md).

## Known-limitation candidates surfaced by RC4.1 (appended to
docs/KNOWN_LIMITATIONS.md)

- SGLang diffusion scheduler spins one core while idle (upstream defect;
  mitigated by session-scoped servers).
- /health 200 does not imply generation readiness (use
  scripts/server_readiness.py).
- Unbudgeted ad-hoc requests default to full-song budgets — degenerate
  inputs should go through scripts/input_budget.py prechecks.
