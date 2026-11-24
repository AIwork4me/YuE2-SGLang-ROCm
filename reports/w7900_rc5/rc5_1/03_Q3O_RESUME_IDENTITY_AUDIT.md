# RC5.1 P0.3.2 — Q3O Resume-Identity Audit

## Finding (fixed)

`scripts/rc5_q3o_judge.py` resumed with:

```python
if dest.is_file():
    prev = json.loads(dest.read_text())
    if prev.get("status") in ("complete", "not_applicable"):
        results.append(prev); continue
```

Any old receipt with a good status was reused with **zero identity
verification** — exactly the flaw the mission flags: a receipt produced by a
different judge revision, different model weights, different placement,
different prompt or different audio bytes would silently mix into a run.

## Fix (this revision)

1. **Run identity manifest** (`compute_run_identity`) is computed at start-up
   and written atomically to `<out>/identity.json`: judge source sha256,
   MoE-block source sha256, evaluator release + runtime hashes, model
   revision + **content hash of every safetensors shard + config file**,
   prompt hashes, q3o-config hash, decoding-config hash (greedy, eos 151645,
   seed 1234), precision, attention backend, torch/hip/transformers
   versions, placement config, tie-break policy. `identity_sha256` binds it.
2. **Directory mixing refused**: if `<out>/identity.json` exists and differs
   in ANY frozen key, the run exits 3 listing the drift — a different
   configuration must use a different output directory.
3. **Per-receipt reuse rule** (`receipt_reusable`, pure function): reuse only
   when status ok AND `identity_sha256` matches AND the receipt's
   `audio_sha256` matches a freshly measured hash of the audio bytes. The
   row's `audio_sha256` from official `prepare_inputs` is additionally
   cross-checked (mismatch = FATAL, audio changed).
4. Non-reusable receipts are **preserved** as
   `q3o.superseded-<ts>-<reason>.json` (never overwritten in place); all
   receipts are written atomically (tmp + rename; a serialisation failure
   cannot damage an existing receipt — negative-tested).
5. Legacy RC5 receipts (no identity fields) are never reused — the old
   rounding-defective judge outputs (retained pilot1 run) are thereby
   refused structurally, in addition to the differing `judge_source_sha256`.

## Negative controls

`tests/test_rc5_q3o_resume.py` (9 tests, torch-free): matching receipt
reusable; `not_applicable` reusable only with matching identity; failed
status never reused; different judge code / audio / legacy-no-identity
never reused; identity drift detects every frozen key (code, MoE source,
torch, placement, tie-break, model revision) while ignoring wall-clock;
atomic write round-trip and serialisation-failure safety.

## Frozen disclosures preserved

The pilot disclosures stand: three placements once gave 5.0/4.83/4.83 (now
root-caused as the unpinned tie-break, see
`03_Q3O_REAL_ROUTER_ANALYSIS.json`: 18–20% of routed slots sit on exact
boundary ties); official CUDA/vLLM tie rule unknown → no equivalence claim;
CPU/GPU placement is part of the run identity.
