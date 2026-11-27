# DEVELOPER_FRICTION_LOG.md — RC6 C6: what a fresh developer actually hit

Recorded LIVE during the Mode 2 fresh-clone execution (nothing invented).
Friction is more valuable than a bare PASS: each item is a real obstacle a
new developer would meet, with its fix.

| # | Friction (symptom) | Where | Root cause | Fix shipped | Fix verified |
|---|---|---|---|---|---|
| F-001 | `reference install` failed: `/…/sglang-latest/python is not a valid editable requirement` — rc5_install_sglang.sh expects the upstream checkout to exist, but the CLI's install step never cloned/checked out/patched it | `scripts/reference_cli.py cmd_install` | the CLI delegated to a script whose preconditions (frozen checkout + patch) it did not establish | `cmd_install` now performs clone → checkout c67d541a → apply import-guard patch (repo-root absolute path) → install, with an already-at-head fast path | YES: the fresh workspace completed install with `SGLANG_INSTALL_RC=0`, import path inside the fresh workspace, tree head c67d541a |
| F-002 | Network clone of the upstream fork through this host's egress proxy crawled (~7 MB in 6 min) | `git clone https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork.git` | documented site egress-proxy intermittency (KNOWN_LIMITATIONS #10) | documented workaround: clone from a local git mirror and VERIFY identity (HEAD == c67d541a + patch sha + runtime manifest) — identity, not provenance of bytes, is the contract | YES: local-mirror clone → HEAD c67d541a → patch applied → `yue2_runtime_sha256 342b2f53…` EXACTLY matches the frozen reference |
| F-003 | `download_pins.py` cannot run with system python (no `huggingface_hub`) | fresh clone, R04 pin verification | the script assumes the generation venv interpreter | CLI `install` step 2 runs it with the venv python; for pure verification the model pins were hash-checked directly (sha256 match both models) | YES: `models/YuE2-3B/model.safetensors` and Vae `model.safetensors` sha256 MATCH the frozen pins |
| F-004 | `finalize_candidate.py` exits rc=3 silently without YUE2_WORKSPACE set | first-song flow before the CLI fix | module-level workspace resolution is strict (by design) | `reference generate` now runs finalize with the workspace env; documented in the CLI contract | YES: finalize rc=0 after env set |
| F-005 | `rc6_verify_results.py` initially FAILED the first song (field-path bugs: nested weight hashes, flat config keys) | A5.6 verification tool | the tool's expectations did not match the real bundle schema | fixed paths + added runtime_sha256 check; the FAILURE ITSELF is the negative-control evidence that the tool does not pass unverifiable identity | YES: same run now VERIFIED_REFERENCE_RUN; frozen campaign still verifies identically |

## What was NOT friction

- environment build (AMD wheels): clean, hash-gated, ~6 min
- doctor / GPU identity: first-try PASS
- runtime manifest proof: exact reference match first try
- evidence packaging (`package-evidence`): rc=0 first try
