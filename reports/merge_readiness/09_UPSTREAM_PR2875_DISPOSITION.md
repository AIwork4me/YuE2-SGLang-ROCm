# 04 — Upstream Contribution Hygiene: PR #2875 Disposition (2026-10-26)

PR under review: https://github.com/sgl-project/sglang-omni/pull/2875
("Fix/yue2 long lyrics", owner **AIwork4me**, base `main`,
head `fix/yue2-long-lyrics` @ `4c089d193f1186aeb40609ac4913273db9cdea95`,
4 commits, OPEN, not draft).

## Findings (GitHub API, refreshed 2026-10-26)

PR #2875's commit list is exactly:

| # | Commit | Author | Content |
|---|---|---|---|
| 1 | `7d34d6e0` | yiakwy-xpu-ml-framework-team | "migrate yue2 supprot from SGLang to SGLang-Omni" (= the author's `add_yue2` first commit) |
| 2 | `85ae4b73` | yiakwy-xpu-ml-framework-team | "update" (= the author's `add_yue2` HEAD, identical to PR #2540 head) |
| 3 | `4ad6658b` | AIwork4me | fix(yue2): allow full-song lyrics in speech requests |
| 4 | `4c089d19` | AIwork4me | test(yue2): synthetic long-input case; neutralize cap-override comment |

Because the branch was cut from the author's `add_yue2` and the PR targets
`main`, its diff-vs-main displays the **entire YuE2 implementation** (29
files) even though commits 3–4 are a two-commit long-lyrics fix.

## Analysis against the three mission questions

**1. Does it duplicate #2540?** Yes — commits 1–2 are byte-identical to the
author's `add_yue2` branch that PR #2540 already delivers. Merging #2875 as-is
would merge the author's implementation through a PR they do not own, with a
misleading title, bypassing #2540's review state.

**2. Does it contain unique required fixes?** No. Commits 3–4 (the
long-lyrics fix + regression test) are **identically available through the
author-fork PR #2** (`yiakwy-xpu-ml-framework-team/sglang-omni#2`, head
`4c089d19` — same SHA), which targets the author's `add_yue2` branch — the
correct integration vehicle per the rehearsed sequence
(`docs/YUE2_UPSTREAM_AUTHOR_HANDOFF.md`). Nothing would be lost by closing
#2875: the branch `fix/yue2-long-lyrics` remains on the AIwork4me fork.

**3. Retarget, replace, or close?** **Close, with a redirect comment.**
- Retargeting #2875 to the author's `add_yue2` would exactly duplicate
  author-fork PR #2 (same head SHA) — pointless double review surface.
- "Replacing" has no meaning here: the fix is already in review in the right
  place.
- Keeping it open invites a maintainer merging the full YuE2 implementation
  under a "long lyrics" title without the author's (#2540's) context — the
  exact failure mode the mission warns about ("avoid creating competing
  full-size upstream YuE2 PRs").

## Recommended exact action (owner executes)

1. Post the close comment (draft below).
2. Close PR #2875 (keep the branch — do not delete; it is PR #2's head).
3. No other change: author-fork PRs #1/#2 and the style commits remain the
   single review surface, feeding the author's `add_yue2` → #2540.

Per mission constraints this session did NOT close or comment on anything —
both actions are outward-facing and remain with the owner.

## Draft close comment for #2875 (ready to post)

> Closing this in favor of the narrower review surfaces — my apologies for
> the noise.
>
> This branch was cut from the author's `add_yue2`, so the PR diff shows the
> full YuE2 implementation, but its actual content is just the long-lyrics
> input-cap fix. That fix is already open for review as
> yiakwy-xpu-ml-framework-team/sglang-omni#2 (same commits
> `4ad6658b`/`4c089d19`), targeting the author's `add_yue2` branch where the
> YuE2 integration is being staged for #2540. The YuE2 implementation itself
> belongs to #2540 and should land through the author's branch, not a
> third-party PR.
>
> Maintainers: nothing here needs merging separately — #2 carries the fix.

Status: analysis PASS; disposition recommendation **close + redirect**;
execution deferred to owner (as required).
