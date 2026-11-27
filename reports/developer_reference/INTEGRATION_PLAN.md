# INTEGRATION_PLAN.md — RC6 D2: consolidated review strategy

## Change classification (the whole RC6 diff vs 57e81c2, by topic)

| Topic | Files | Review focus |
|---|---|---|
| 1. ROCm compatibility | `patches/*` (unchanged), install tooling | none new — reference only |
| 2. Runtime lifecycle | none changed (reused as-is) | — |
| 3. GPU identity & readiness | none changed (reused) | — |
| 4. Benchmark driver | `scripts/campaign_ops/rc6_corrected_scoreboard.sh` (new) | small wrapper, delegates to frozen evaluator |
| 5. Evaluator adaptation | `scripts/rc5_asr_vllm_native.py`, `scripts/rc5_score_transcripts.py` (hardened, math untouched), `scripts/rc6_asr_identity.py` (new lib) | fail-closed resume + validation; GREEN regression included |
| 6. Scientific audit | `scripts/rc6_determinism_closure.py`, `rc6_per_paired_attribution.py`, `rc6_evaluator_provenance.py`, `rc6_q3o_comparator.py`, `rc6_evidence_freeze.py`, `rc6_corrected_scoreboard_driver.py` | read-only analyses over frozen evidence |
| 7. Developer documentation | `docs/QUICKSTART_W7900.md` (canonical rewrite), `docs/{KNOWN_LIMITATIONS,COMPATIBILITY_MATRIX,TROUBLESHOOTING,EVIDENCE_INDEX,BENCHMARK_REPRODUCTION}.md` (hygiene), `README.md` | stale-statement corrections only |
| 8. Developer tooling | `scripts/reference_cli.py`, `scripts/rc6_verify_results.py`, `examples/first_song/*` | new golden-path surface |
| 9. Tests & controls | `tests/test_rc6_asr_identity.py` (20 controls), GPU negative controls | each failure mode demonstrably detected |
| 10. Release evidence | `reports/developer_reference/**` (all RC6 receipts) | machine-readable; public-safe |

## Stacked-PR strategy (decision: keep the stack)

The open PR stack #8–#19 is LINEAR (all contained in #19 — see
PR_DEPENDENCY_GRAPH.md). RC6 adds one more level:
`mission/rc6-developer-reproduction-reference` on top of #19's head.

- We do NOT create a separate consolidation branch: it would duplicate diffs
  that already exist as traceable cut points and burn maintainer attention.
- The RC6 PR body classifies changes by the table above so a reviewer can
  review by topic without walking the whole stack.
- Merge order for the owner: (#19 or its successor) → RC6 PR; the
  intermediate PRs close as their content is contained (except #8 — owner
  decision recorded in PR_DEPENDENCY_GRAPH.md §3).
- Merge-time gate (recorded in the release ledger): when the mission chain
  eventually merges toward main, re-run BOTH public-evidence guard suites
  on the merge result (main's #7 redaction + the chain's guards evolved
  independently).

## What RC6 deliberately does NOT do

- No rebase onto main; no force-push; no PR merges/closures; no history
  rewriting; no changes to frozen evidence or frozen benchmark protocol.
