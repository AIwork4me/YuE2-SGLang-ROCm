# 05 — Security and Independent Review (merge-readiness mission, 2026-10-26)

## Independent reviews

### SGLang integration branch — three fresh review passes (today)

Full texts: `reviews/REVIEW_A_ROCM_CORRECTNESS.md`,
`reviews/REVIEW_B_NVIDIA_PRESERVATION.md`,
`reviews/REVIEW_C_MAINTAINABILITY.md` (each written by an independent
reviewer agent with repository access; P0/P1 protocol enforced).

| Review | Verdict | P0 | P1 | P2 | P3 | Disposition |
|---|---|---|---|---|---|---|
| A — ROCm correctness | PASS-WITH-P2s | 0 | 0 | 2 | 6 | P2-A fixed (`torch.version.hip` pip-fallback guard); P2-B + P3s documented as author follow-ups |
| B — NVIDIA preservation | PASS-WITH-P2s | 0 | 0 | 2 | 3 | duplication note resolved by P0-1 relocation; H800 physical validation remains author-owned |
| C — maintainer simulation | **FAIL → resolved** | 2 | 2 | 2 | 4 | **all four P0/P1 fixed in `44c8fa51f` and revalidated** (121/121 tests + fresh E2E re-smoke) |

Highlights of what the reviews verified beyond the mainline validation:
gates evaluated live on gfx1151; aten fallback compared against an fp32
SDPA reference (max err 0.0048); all six fast-path function ASTs identical
to the author's code; env-var truth tables identical on supported devices;
36-file/+8 115/−1 surface confirmed YuE2-scoped with textbook attribution
(author chain intact, `def437fb` as a true merge, author-date-preserving
cherry-pick).

### SGLang-Omni integration — review basis

The 31-file content delta is **identical to the tree that already received
three-role independent review in the prior closure mission**
(`reports/final_merge_closure/09_INDEPENDENT_REVIEWS.md` — ROCm technical /
scientific benchmark / maintainer simulation, all PASS; base `85ae4b73`
re-verified unchanged today). Today's additions on top are: (a) the
bit-exact rehearsal reproduction (SHA equality is itself the strongest
identity check), and (b) the main-merge whose both-sides surface is a
single file, verified by content inspection and by that file's tests
passing (60/60). A fresh content re-review would duplicate the prior
mission's artifacts; the delta-identity argument is recorded here instead.

## Security review

- **Request-schema bounds** (SGLang `entrypoints/yue2_api.py`): pydantic
  model with typed, bounded fields (`ode_steps` 1–128; `seed` ≥ 0; token
  and frame budgets are positive ints consumed as generation budgets).
  Free-text fields (style/lyrics/abc) are inherently unbounded strings —
  same posture as the author's original route and consistent with the
  long-lyrics fix's model-specific acceptance; the input-cap policy itself
  was reviewed in the prior mission (bounded, model-gated, other models
  unaffected — regression tests green today).
- **No new dependencies** introduced by either branch; no network egress,
  no secrets, no eval/exec in the delta (checked by review C).
- **The ROCm host-boot overlay** binds unavailable ops to `None` with
  call-time failure — no silent fallback to incorrect math; it cannot
  weaken CUDA hosts (import-success path unchanged).
- **Untrusted-content note**: `model_index.json`-driven pipeline selection
  is upstream's existing mechanism; the integration adds no new
  file-system or code-loading surface beyond the (now packaged, imported
  via normal module import) router — strictly narrower than the original
  `importlib.util.spec_from_file_location` filesystem loader it replaces.
- **Honesty of evidence**: all "PASS" claims above correspond to commands
  run on this machine with logs/artifacts retained (`runs/
  merge_readiness/…`, `logs/server_*.log`); H800/NVIDIA hardware
  execution is explicitly NOT claimed anywhere; GPU CI remains blocked on
  the maintainer label.
