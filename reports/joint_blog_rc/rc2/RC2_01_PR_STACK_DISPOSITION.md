# RC2_01b — PR Stack Disposition (owner-gated; nothing closed/merged here)

Live state re-verified 2026-11-19 (gh): all of #8–#15 OPEN, Draft, MERGEABLE.

| PR | Head | Content vs RC | Disposition recommendation | Rationale |
|---|---|---|---|---|
| #8 | `9a230d5` | Arm A evidence preservation (journal quarantine, honest PER gates) on a diverged `run_wsb_torch.py` lineage | **Close as superseded** after owner review | Implementation superseded by the integrated lineage that actually completed the fresh 384/384 Arm A run; guarantees live on as ported tests (torn tail, last-status-wins, incomplete-tail refusal, interior-corruption fail-closed) — verified present and green in #15 |
| #9 | `cdff9312` | fresh-image final closure (env rebuild, RCA F1–F6, P4.1 acceptance, P8 security) | **Absorbed** (ancestor of #13/#14/#15) | Fully contained in the RC stack; no action beyond eventual branch cleanup |
| #10 | `87561253` | CPU-only risk closure (public evidence hygiene, PER analysis, release gates) | **Close as superseded** when #15 merges | Content in #15; branch history preserved |
| #11 | `4d9f4a2d` | C2 scientific/provenance hardening | **Close as superseded** when #15 merges | Same |
| #12 | `aa3f34f5` | C2.1 fail-closed closure (atomic package, no-clobber, provenance chain, TOCTOU) | **Close as superseded** when #15 merges | Merged content-wise into #15 with 2 resolved conflicts; mutation controls 5/5 + review's F6 confirm behavior |
| #13 | `f7fda39` | image-swap resume hardening (C1–C4, restoration/evaluator tooling) | **Close as superseded** when #15 merges | Ancestor of #14/#15 |
| #14 | `fee027d` | M1 runtime/lifecycle fixes (= live campaign checkout) | **Review + fold into #15** (or merge #14 then rebase #15) | Contains the M1.1–M1.3 fixes; the RC2 fix branch carries their successors |
| #15 | `66b5a13` | integrated RC | **RC candidate**; add RC2 fixes (Draft PR from `mission/joint-blog-rc2`), then owner review → merge decision | 119 ahead / 4 behind main is topology-only (content reconciled, RC2_00 §3); recommend final retarget/rebase review at release time, not an automatic merge |

**RC2 fix branch** (`mission/joint-blog-rc2`, this review): P1/P2/P3 fixes +
18 regression tests + mutation-control pinning. Intended flow:
`#15 ⊕ rc2-fixes → final RC → owner-gated merge train → main`.

Rules honored in this session: no PR closed, no merge, no force-push, no
upstream submission, no external communication.
