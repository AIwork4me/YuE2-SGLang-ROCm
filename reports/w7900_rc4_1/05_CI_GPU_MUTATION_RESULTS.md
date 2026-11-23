# RC4.1 M5.2 — Mutation control results

Runner: `scripts/mutation_controls_rc41.py` (each mutation applied to the
working tree, targeted battery executed, tree git-restored; requires clean
tree). Raw JSON: `05_CI_GPU_MUTATION_RESULTS.raw.json`.

Two mutations initially SURVIVED (M7: a real operator-precedence bug in
the new timeout test `A and B or C`; M10: the count check accepted the
number appearing anywhere instead of the canonical claim form). Both test
gaps were CLOSED and the mutations re-run to KILLED — the mutation suite
did its job. M2/M8 first round NOT_RUN (stale mutation patterns) — fixed
to match real code.

| ID | Mutation | Result | Killed by |
|---|---|---|---|
| M1 | remove GPU device guard (mismatch -> ok) | **KILLED** | tests/test_gpu_identity.py (status assertions) |
| M2 | downgrade GPU mismatch to warning (ok=True) | **KILLED** | tests/test_gpu_identity.py (ok is False assertions) |
| M3 | dead scheduler returns READY | **KILLED** | tests/test_server_readiness.py::test_worker_dead_http_200_is_not_ready |
| M4 | readiness only checks HTTP /health | **KILLED** | tests/test_server_readiness.py (identity/pid-reuse/degraded set) |
| M5 | gpu_lock released immediately after acquire | **KILLED** | tests/test_run_with_server.py::test_5_gpu_lock_held_for_whole_session |
| M6 | skip server cleanup on wrapper exit | **KILLED** | tests/test_run_with_server.py::test_2_driver_failure_still_stops_server |
| M7 | repeated-tags timeout made unbounded (inf) | **KILLED** | tests/test_input_budget.py::test_timeouts_bounded |
| M8 | delete input validity checks (always OK) | **KILLED** | tests/test_input_budget.py::test_repeated_tags_rejected_bounded |
| M9 | mix an old run row into the evidence CSV | **KILLED** | tests/test_evidence_consistency_rc41.py::test_real_repo_evidence_consistent + duplicate detection |
| M10 | cite 791 rows as 790 in the final report | **KILLED** | canonical claim check via test_real_repo_evidence_consistent |
| M11 | wrong GB/GiB conversion (51.5 'GiB') | **KILLED** | GiB mislabel guard (test_real_repo + unit) |
| M12 | stale PENDING reintroduced in verdict JSON | **KILLED** | stale-PENDING guard (test_real_repo + unit) |

**Final: 12/12 KILLED, 0 SURVIVED.**
