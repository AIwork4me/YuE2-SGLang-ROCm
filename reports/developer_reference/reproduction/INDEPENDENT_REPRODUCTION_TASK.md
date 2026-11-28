# INDEPENDENT_REPRODUCTION_TASK.md — RC6 C4: hand-off task for an independent engineer/agent

You are handed this task BECAUSE you did not build this repository. Execute
from a machine with an AMD gfx1100-class GPU (or state clearly what you
cannot run). Use ONLY this repository's public documentation and the
authorized asset pins. Do not ask the original executor for oral
instructions: if anything is unclear or fails, record it as
**documentation friction** (that is the measurement).

## Your deliverables

1. A filled copy of the receipt table below (R-matrix).
2. A friction log: every ambiguity, missing dependency, hidden assumption,
   retry count, manual intervention, and your time-to-first-verified-song.
3. An honest verdict per item — PASS / FAIL / NOT_RUN with reason. Never
   relabel.

## Steps (from the repository's public docs)

```bash
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git && cd YuE2-SGLang-ROCm
python3 scripts/reference_cli.py doctor                      # R02
python3 scripts/reference_cli.py install                     # R03-R05 (pinned stack, hash-gated)
python3 scripts/reference_cli.py generate \
  --lyrics examples/first_song/lyrics_en.txt \
  --style examples/first_song/style.txt \
  --seed 831001 --out-dir $WS/runs/my-first-song             # R06
python3 scripts/reference_cli.py verify \
  --run-dir $WS/runs/my-first-song                           # R07 (expect VERIFIED_REFERENCE_RUN)
python3 scripts/reference_cli.py benchmark --mode pilot      # R09 (optional, ~1 h GPU)
python3 scripts/reference_cli.py compare --run-dir <pilot>   # R19
```

Reference numbers you may compare against (with scope labels):
`reports/developer_reference/06_PERFORMANCE_REFERENCE.md` and the frozen
scoreboard `reports/w7900_rc5/rc5_1/06_FIVE_METRIC_SCOREBOARD.csv`.

## Receipt table (fill per item)

| # | Item | Expected | Actual | Exit code | Wall time | Evidence path | Result | Failure reason | Fix |
|---|---|---|---|---|---|---|---|---|---|
| R01 | Clone | repo at the release-candidate SHA | | | | | | | |
| R02 | doctor | no blockers | | | | | | | |
| R03 | GPU compute | GPU_EXECUTION_VERIFIED | | | | | | | |
| R04 | pins | exact sha matches | | | | | | | |
| R05 | runtime identity | yue2_runtime_sha256 342b2f53… | | | | | | | |
| R06 | first song | complete piece | | | | | | | |
| R07 | verify | VERIFIED_REFERENCE_RUN | | | | | | | |
| R08 | perf receipt | time recorded | | | | | | | |
| R09 | pilot | 10 candidates | | | | | | | |
| R13 | negative controls | detected | | | | | | | |
| R17 | GPU release | lock free | | | | | | | |
| R18 | package-evidence | rc=0 | | | | | | | |

## Rules

- Assets: only the SHA-pinned public set; nothing else. Report the source of
  every download (fresh vs hash-verified cache).
- GPU results must come from the GPU (the tools are fail-loud; a CPU
  fallback anywhere is a BUG to report).
- Pilot numbers are never compared with full-benchmark numbers.
- Report failures verbatim (symptom → diagnostic → what you tried). A FAIL
  from you is more valuable to this project than a generous PASS.
