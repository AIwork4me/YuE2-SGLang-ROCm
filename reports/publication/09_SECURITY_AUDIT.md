# 09 — Security Audit (Phase 9, publication-readiness mission)

**Audit date:** 2026-11-11/12 · Scope: this branch (`feat/yue2-rocm-publication-readiness`) and the runtime environment used for the campaigns.

## 1. Secrets and credentials

| Check | Result |
|---|---|
| Token patterns in tracked files (ghp_/gho_/AKIA/sk-/hf_/xox/PRIVATE KEY) | CLEAN (full-tree scan 2026-11-11; repeat before every push via pattern scan) |
| GitHub token storage | `/workspace/.gh-token`, mode 0600, OUTSIDE the repo tree; never echoed into logs |
| Token in remote URLs / git config | CLEAN (https remote without embedded credentials) |
| `.gitignore` hygiene | `hf_token*`, `.env`, venvs, runs/, models/, benchmark/ excluded |
| Historical evidence files | Prior full-history audit (2026-10-17, `docs/PUBLIC_SECURITY_REVIEW.md`): 93 commits/352 blobs, no secrets — not re-litigated, still valid |

## 2. Supply chain and downloads

| Check | Result |
|---|---|
| Every pinned download SHA256-verified | YES (`download_pins.py` aborts on mismatch; verified live this mission — ALL PINS VERIFIED) |
| Evaluator assets | 56/56 pinned files sha256-verified (`fetch_eval_assets_hub.py` + official `verify_assets`) |
| HTTP downgrade for convenience | NONE (HTTPS only; proxy 503s handled by retry, never by protocol downgrade) |
| Archive extraction | Hardened: path-traversal + link rejection + `filter="data"` (Issue E fix) |
| `curl \| bash` patterns | NONE in scripts or docs (enforced by `test_docs_contract.py`) |
| pip build isolation hazard | Mitigated: `--no-build-isolation` for editable installs; the CUDA-torch build-requirement pull is documented and guarded (RCA-3) |
| Wheel origin | AMD multi-arch index / download.pytorch.org / PyPI via egress proxy only |

## 3. Machine identifiers and information disclosure

| Check | Result |
|---|---|
| `/home/amd/...`, `/raid/...`, `/tmp/opencode` in scripts | ELIMINATED from defaults (workspace contract); historical evidence files and patch headers retain them as immutable provenance records (documented, low risk) |
| Hostnames in new evidence | Only in run receipts where they identify the rig (consistent with historical practice; no internal addresses beyond the egress proxy host which is already public in env docs) |
| Egress proxy address | Appears in docs as environment documentation — acceptable (no credentials attached) |

## 4. Runtime and service posture

| Check | Result |
|---|---|
| Server binding | 127.0.0.1 only (default in serve scripts) |
| Shell injection | Driver payloads built via JSON/argparse, no `eval`/string-into-shell of user data; `shell=True` not used in campaign drivers |
| Unsafe deletion | Quarantine-not-delete semantics in drivers; `rm -rf` only on mission-owned fresh run dirs (documented) |
| Process supervision | PID-verified safe stop (`server_identity.py`); no pkill-pattern footguns in shipped scripts (one incident during this mission used an interactive pkill that matched its own shell — documented in RCA ledger, not shipped code) |
| Container egress | Via authenticated site proxy; no inbound exposure |

## 5. Findings register

| # | Finding | Severity | Status |
|---|---|---|---|
| S-1 | Historical `evidence/per_song.jsonl` embeds `reference_lyrics` (copyrighted lyrics) in a (currently private) repo going public | HIGH for publication | OPEN — owner decision (LQ-1) |
| S-2 | Machine path residues in historical evidence/patch headers | LOW | ACCEPTED (immutable provenance; disclosed) |
| S-3 | Egress proxy intermittency forces retry patterns that could tempt HTTP downgrades | LOW | MITIGATED (policy: never) |
| S-4 | Interactive-shell incidents (self-matching pkill) | INFO | Documented; no shipped-code impact |

**Verdict:** PASS for code/infra security with one publication-blocking content-rights item (S-1 = LQ-1) that requires an owner decision; it is tracked in the gate ledger under G13.
