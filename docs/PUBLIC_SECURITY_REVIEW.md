# Public Security Review — AIwork4me/YuE2-SGLang-ROCm

Review date: 2026-10-17 · Repository: `AIwork4me/YuE2-SGLang-ROCm` (public) ·
Scope owner: repository owner (AIwork4me)

This page documents a full-history security audit performed before the 2026-10-17
documentation update. It is intentionally published in a redacted, public-safe form.

## 1. Methodology

- **Coverage**: every reference advertised by the repository at audit time — 7 branch
  heads, 4 pull-request head refs (`refs/pull/1..4/head`), all **93 commits**
  reachable from them (full parent traversal), all **91 trees** and all **352 unique
  blobs** (21.66 MB) in history, plus workflow definitions and a sample of GitHub
  Actions run logs.
- **Tools** (pinned releases, checksum-verified, positive-controlled before use):
  gitleaks 8.30.1 and TruffleHog 3.99.2 scanning the complete materialized history
  (not just the working tree), plus an independent third sweep with 18 secret-category
  regular expressions (GitHub PAT/fine-grained tokens, Hugging Face, ModelScope,
  OpenAI/Anthropic, AWS, GCP service-account JSON, private key blocks, SSH key
  material, Authorization/Bearer headers, session cookies, password assignments,
  credential-bearing URLs, npm/Slack/PyPI tokens, JWTs) and Shannon-entropy analysis
  with human triage of every high-entropy hit.
- **Categories checked**: leaked credentials of all listed families, private
  keys/certificates, internal infrastructure disclosure (hostnames, DNS names, IPs,
  proxies, paths), personal data, dataset/licensing exposure, Actions logs, and
  commit-message content.

## 2. Result summary

| Check | Result |
|---|---|
| Secret scanning (full history, 2 scanners + custom sweep) | **No true-positive findings.** One gitleaks alert was verified to be a false positive (the words "selection keys" in scientific prose); TruffleHog: 0 findings; custom sweep: 0 hits. All 953 high-entropy strings were individually classified as digests, paths, or base64 artifacts. |
| Credentials in Actions logs (sampled runs) | None (only commit SHAs/dates). |
| Personal data / contact info | None found beyond placeholder strings. |
| Internal infrastructure details | A small number of benign, non-routable environment details (ephemeral lab hostname, internal DNS name, one RFC1918 address) inside frozen environment receipts — retained deliberately as reproducibility metadata; none are secrets or externally exploitable. |
| Dataset / IP review | See §4 — **LICENSE_REVIEW_REQUIRED** (owner item, non-security). |
| GitHub native secret scanning / push protection / Dependabot | **Disabled at audit time** — see §5 (owner action recommended). |

## 3. Limitations

- Scanners passing does not prove absence of unknown credentials; secret detection is
  heuristic.
- `refs/pull/N/merge` refs were not exposed by GitHub (HTTP 404) and could not be
  enumerated; dangling objects not referenced by any ref are not enumerable via the
  API; GitHub-side caches and any unknown external clones are outside this audit.
  Fork count was 0 at audit time.
- Actions logs were sampled (4 representative runs of the same single-job CPU
  workflow out of 25).
- The audit was performed through the GitHub REST API (the audit environment's
  egress proxy blocks the git smart-HTTP endpoint); object coverage was validated by
  ref/SHA cross-checks rather than `git fsck`.

## 4. Data-provenance notes for readers

Evidence files in this repository intentionally contain (a) WildSongBench benchmark
prompt text (song lyrics) reproduced verbatim as required inputs, and (b) ASR
transcriptions of model-generated audio. The `m-a-p/WildSongBench` dataset card
currently declares **no license**. These files exist for scientific reproducibility;
no redistribution license for third-party content is claimed (see README §9). The
repository owner is tracking this item with the dataset authors
(**LICENSE_REVIEW_REQUIRED**); no history rewrite is planned.

## 5. Recommended owner actions (not yet performed — require account access)

1. Enable **secret scanning** and **push protection** (Settings → Code security and
   analysis). Both were disabled at audit time on this public repository.
2. Enable **Dependabot alerts/security updates**.
3. Enable **private vulnerability reporting** and add a `SECURITY.md` pointing to it
   (avoid inventing email addresses).
4. Track the WildSongBench licensing question (§4) with the dataset authors.

## 6. Verdict

**No credentials or exploitable secrets were found in any reachable object of this
repository's history.** Two owner-action items remain open (platform security
controls; dataset licensing clarification). This review makes no "zero-risk"
claim — see §3 limitations.
