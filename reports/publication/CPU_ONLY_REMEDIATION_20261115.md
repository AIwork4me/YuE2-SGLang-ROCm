# CPU-only remediation — 2026-11-15

## Scope

Issues C/D from the four-risk review. **No GPU hardware was accessed.**
This change neither fixes nor claims to fix the SGLang AR hang (A)
or concurrent HIP illegal memory access (B). Those remain physical-RCA tasks.

## Fixed in code

1. Worker no longer deletes existing `.partial` candidate bundles.
   Renames are collision-resistant and reject symlinks.
2. JSONL appends use a file lock, durable write loop and fsync.
   Torn final records are quarantined on restart; invalid complete rows
   remain fail-closed. Duplicate event IDs resolve by last status.
3. An exclusive per-run driver lease prevents concurrent launches.
4. A complete, verified candidate lacking a journal record is recovered
   with an explicit provenance marker, not regenerated.
5. Worker crash/timeout is recorded as failure; partial outputs are retained.
6. A write-once harness-source receipt records the active driver/worker
   SHA256. Pre-existing historic journal rows are explicitly tagged as
   lacking this new source receipt instead of retroactively attributed.
7. New CPU fault-injection regression tests cover the above.

## Scientific interpretation

The old PER RCA did not prove that the evaluator was equivalent.
The docs and G6/G9 gates now correctly remain BLOCKED until same-audio
cross-evaluator controls are performed.

## Still blocked

- **A:** SGLang AR-stage hang needs real failure reproduction/stack capture.
- **B:** HIP illegal access when generation and ASR overlap needs physical
  controlled repro; GPU single-tenant policy remains an operational mitigation.
- **D:** a separate security PR deletes/redacts current-tree text-bearing
  evidence, but cannot erase Git history. No claim of full legal closure.

## Test plan

```bash
python3 -m pytest -q tests/test_wsb_torch_resume.py
python3 -m compileall -q scripts
python3 -m pytest -q tests
```

No benchmark was rerun; existing SGLang 384/384 receipts remain untouched.
