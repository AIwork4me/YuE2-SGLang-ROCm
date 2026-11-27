# reports/developer_reference/ — RC6 entry point

**YuE2 on ROCm Developer Reproduction Reference** — everything a developer
or reviewer needs, organized by question. Historical engineering evidence
stays in `reports/w7900_rc5/`, `reports/w7900_rc4*/`, `reports/gfx1100/` …
(Historical Reference; not on the developer critical path).

## I am a developer who wants to run YuE2 on my Radeon GPU

1. `docs/QUICKSTART_W7900.md` (canonical path) — or
   `python3 scripts/reference_cli.py --help`
2. Verify your own results: `scripts/rc6_verify_results.py`
3. Problems: `docs/TROUBLESHOOTING.md`; boundaries:
   `docs/KNOWN_LIMITATIONS.md`, `06_OPERATIONAL_LIMITS.md`
4. What to expect: `06_PERFORMANCE_REFERENCE.md`,
   `06_COMPATIBILITY_MATRIX.json`

## I am a scientific reviewer

| Question | Read |
|---|---|
| Is generation deterministic? | `01_GENERATION_DETERMINISM.md` (+ `01_*_VERDICT.json`) |
| Can I trust the PER numbers? | `02_ASR_IDENTITY_CONTRACT.md`, `02_EVALUATOR_PROVENANCE_VERDICT.json`, `02_ASR_RESUME_RCA.md` |
| Why did PER differ, exactly? | `03_PER_PAIRED_ATTRIBUTION.json`, `03_SELECTION_RECONCILIATION.json` |
| Corrected-selection scoreboard? | `03_CORRECTED_SCOREBOARD.csv` |
| Q3O: what exactly is claimed? | `04_Q3O_CONTRACT.md`, `04_Q3O_NUMERICAL_BOUNDARY.md`, `04_Q3O_MUTATION_REVIEW.json` |
| All gates, honestly | `FINAL_RELEASE_GATE_LEDGER.json`, `INDEPENDENT_REVIEW.md` |

## I am the YuE2 author / an AMD engineer

- Author package: `author/AUTHOR_REVIEW_PACKAGE_EN.md` (+ acceptance
  matrix, CUDA runbooks, comparison schema, request draft)
- AMD package: `AMD_ACCEPTANCE_PACKAGE_EN.md` (+ `AMD_ACCEPTANCE_MATRIX.json`)
- Upstream patch plan: `UPSTREAM_PATCH_OWNERSHIP.md`; PR topology:
  `PR_DEPENDENCY_GRAPH.md`

## I maintain this repository after RC6

`MAINTENANCE_SCHEMAS.json`, `LICENSE_AND_SECURITY_REVIEW.md`,
`PR_DEPENDENCY_GRAPH.md`, `configs/developer.lock.yaml`

## Release candidate

`RELEASE_NOTES.md`, `RELEASE_MANIFEST.json`, `RELEASE_VALIDATION.md`,
`PUBLIC_CLAIMS_MATRIX.md` — Developer Reproduction Reference v1.0-rc1
(prepared, not published; publication needs owner authorization).
