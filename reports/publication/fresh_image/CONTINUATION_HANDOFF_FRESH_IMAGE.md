# CONTINUATION HANDOFF — Fresh Image Mission (session 1 → session 2+)

**Written:** 2026-11-15T04:15Z · **Branch:** `mission/w7900-fresh-image-final-closure`
(local; **push blocked: no GitHub credentials in this image** — first action for
the owner/next session with credentials: `git push -u origin mission/w7900-fresh-image-final-closure`)

## 1. What this session accomplished (all on the fresh image, evidence in git)

- **P0** environment verified (W7900D/gfx1100 48GB, ROCm 7.2.1 preserved, driver 6.16.13);
  GPU smoke corrected-and-passed (test-authoring bugs disclosed).
- **P1** reconciliation: no prior /data survived; historical receipts retained as
  HISTORICAL only; everything fresh must be regenerated (being done).
- **P2** all three environments built + verified on GPU: env A (torch
  2.10.0+rocm7.1, yue2-infer 0.1.3), env B (torch 2.12.0+rocm7.14.1
  device-gfx1100, SGLang ced0ef7d + patches re-applied on verified pristine),
  env C (evaluator chain 0006→0007→0009→**0010 formalized**, bit-exact vs lock;
  assets hash-verified; venvs + AMD substitution done; offline prepare PASS).
- **P3** RCA-F1–F6 fixed with regression tests (31 green): partial-dir
  quarantine, fsync journal + crash-tolerant reader, exact run identity
  (stable contract + driver_protocol; volatile fields excluded — live bug
  found & fixed during campaign), GPU ownership lock (flock, zombie-safe),
  scoring rerun semantics, gate-status vocabulary.
- **P4.1** API acceptance **13/14 PASS** (staged API retested under the real
  contract; `close()` memory retention documented as a finding).
- **P8** security: LQ-1 confirmed at HEAD; round-trip-verified redaction
  tooling + redacted copies committed; SECURITY_FINAL + LICENSE_FINAL;
  owner decision required (Option A/B/C).
- **P6 tooling** ready: `per_tail_analysis.py` (consistent denominators),
  `build_per_reference_package.py` (cross-backend kit).

## 2. Live processes (session-independent, setsid-detached)

| PID | Role | Notes |
|---|---|---|
| 9088 | `/opt/venv/bin/python /data/yue2/mission_chain.py` | stage machine; currently `armA_campaign`; auto-audits, auto-scores, then Arm B |
| 16537 | Arm A campaign driver (`run_wsb_torch.py`, run-id `armA_full_20261115f`) | holds GPU lock; **resume-safe**: relaunch with `/data/yue2/run_armA_campaign.sh` |
| (watchdog) | `armA_watchdog.sh` | stall diagnostics only (no auto-restart, no pkill) |

Progress at handoff: **16+/384** complete, ~10 min/candidate, **ETA ~67 h**.
Log: `/data/yue2/logs/armA_armA_full_20261115f.log`; journal:
`/data/yue2-runs/armA_wsb_full/generation_manifest.jsonl` (`grep -c '"status": "complete"'`).

## 3. Command sequence for the continuation session

1. `git -C /workspace/YuE2-SGLang-ROCm log --oneline -3` (expect `6796040` or later)
2. Check campaign: `grep -c '"status": "complete"' /data/yue2-runs/armA_wsb_full/generation_manifest.jsonl`
3. If driver died: `setsid nohup /data/yue2/run_armA_campaign.sh &` (resume-safe)
4. mission_chain handles: audit (FULL required) → scoring PER+SongBench →
   MuLan+AMC → Arm B stages. Score receipts land in
   `/data/yue2-runs/armA_wsb_full/{scores,additional}/`.
5. After Arm B completes: `scripts/summarize_campaign.py` for both arms →
   `evidence/publication/fresh_image/{armA,armB}/` → final reports (P10–P12).
6. SGLang-Omni (P5.4): PR branch fetched at `/data/yue2/upstream/sglang-omni` (pr2540).

## 4. Gotchas added this session (on top of the 14 in the old handoff)

15. `pgrep -f` self-matches the querying shell — verify arms with log files or
    exact `ps` filters, never bare pgrep booleans.
16. pytest fixtures must NOT extract the evaluator tarball into /tmp (4G tmpfs)
    — use `/data/yue2/tmp` (fixed in tests).
17. `memory_budget_gib` is a HARD cap minus 2 GiB reserve — never below ~8 for
    the 3B model (official: 24).
18. `yue2` staged API: `plan(request=SongRequest(...))`, `Sampling()` has no
    seed, `decode()` returns raw audio (see PYTORCH_API_ACCEPTANCE corrections).
19. The bash tool kills long foreground commands — ALWAYS `setsid nohup ... &`
    for anything >60s, then poll logs.
20. Zombie PIDs (unreaped children of init) look "alive" to naive `os.kill(pid,0)`
    — gpu_lock checks /proc stat state (tested).

## 5. Blockers / owner decisions

- **Credentials**: no GitHub push possible from this image (gh-proxy clone,
  no tokens). Owner: push the branch (12 commits ahead of fdfc0ac at writing).
- **LQ-1**: lyric-bearing files at HEAD + history — Option A/B/C decision
  (SECURITY_FINAL.md §1.3).
- **Upstream submissions**: all gated on owner review (UPSTREAM_PR_PLAN.md).

## 6. Honest mission state

The multi-day GPU campaign chain is armed and producing verified candidates.
Gates G5–G14, G16–G17, G19 are NOT_TESTED by design (queued behind the
campaign) and are tracked live in
`reports/publication/fresh_image/FINAL_RELEASE_GATE_LEDGER.json`. Nothing in
this session claimed parity, completion, or upstream resolution without
physical evidence.
