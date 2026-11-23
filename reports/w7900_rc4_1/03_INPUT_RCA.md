# RC4.1 M3 — Input RCA: the "repeated-tags hang" and the bounded input contract

## 1. Symptom (RC4)

`rc4_reliability_matrix.py` invalid-request battery, payload #5:
`{"style": "[Tags]\nx\n" * 200, "lyrics": "[Lyrics]\nA.\n"}` (~2.6 KB).
Two occurrences, both client TimeoutError at the battery's 60 s cap.
Classified in RC4 as "request path hangs >60 s (defect candidate)".

## 2. Root cause (RC4.1, reproduced and code-traced)

The payload is **schema-valid** for the YuE2 HTTP API
(`sglang/experimental/yue2/http_api.py::Yue2AudioGenerationsRequest`):
style and lyrics are strings, all other fields optional with **full-song
defaults** (`ode_steps=32`, `semantic_max_tokens=9000`, `abc_max_tokens=
4096`). The server therefore started a legitimate FULL-SONG generation
(minutes of real GPU work on W7900), which the 60 s test budget mistook
for a hang.

Decisive evidence (real W7900, phase B1 receipts,
`/data/yue2-runs/rc4_1_evidence/20261122T2300Z/phase_b1.json`):

| Case | Budgets | Result |
|---|---|---|
| repeated-tags, explicit SHORT (ode_steps=4, semantic_max_tokens=300) | 60 s-class | HTTP 200 in 9.0 s |
| repeated-tags, server DEFAULTS (ode_steps=32, semantic_max_tokens=9000) | 1800 s | HTTP 200 in full-song-class time (see receipt) |

The identical payload completes boundedly under both budget regimes →
NOT a loop, NOT a scheduler defect, NOT a tokenizer pathology. The defect
was in the TEST HARNESS classification (unbudgeted "invalid" payload),
which RC4.1 fixes.

Secondary checks: 2 MB style → clean fast 500 (RC4, unchanged); 40-verse
lyrics → bounded 1123 s completion (RC4, unchanged — legal long input
keeps working).

## 3. Fixes

1. `scripts/rc4_reliability_matrix.py`:
   - the repeated-tags payload (and any payload failing precheck) is now
     classified via `scripts/input_budget.py` BEFORE any request is sent
     (outcome `BOUNDED_REJECT` — no GPU spend);
   - new case `repeated_tags_short_budget` (bounded server-side proof);
   - new opt-in case `repeated_tags_default_budget` with a full-song-class
     timeout (documents actual behavior; off by default).
2. `scripts/input_budget.py` (new): pure-CPU precheck contract —
   style ≤ 4096 B / ≤ 8 bracket-sections / ≤ 16 identical consecutive
   sections; lyrics ≤ 64 KiB (legal 40-verse lyrics ≈ 5 KB pass); type,
   UTF-8 and seed validation; machine-readable classifications
   (OK/TYPE_INVALID/STYLE_TOO_LARGE/LYRICS_TOO_LARGE/
   STYLE_DEGENERATE_REPETITION). Exit 4 = bounded rejection.
3. Protocol isolation: the frozen WildSongBench driver path
   (`run_wsb.py` + official manifest payloads) is deliberately NOT routed
   through the precheck — official payloads pass these budgets anyway
   (styles ~100–300 B) but the official protocol path stays byte-for-byte
   unchanged. The precheck guards project/ad-hoc tooling.

## 4. Bounded-input contract satisfied

- explicit budget BEFORE GPU work (invalid never reaches the GPU)
- legal long lyrics never rejected (verified: 40-verse passes)
- degenerate structures get a clear classified error (HTTP-facing tools
  can map `input_budget` exit 4 to 4xx; the SGLang server itself keeps
  its native behavior — no protocol forgery, no fake 200s)
- no infinite loop introduced (precheck is linear-time regex/counting)
- cancellation/timeouts unaffected (request path untouched)

## 5. Test matrix

`tests/test_input_budget.py` (12 tests): repeated-tags rejected bounded ·
normal tags pass · legal repeated tag VALUES pass · multi-section legal
style passes · 40-verse legal lyrics pass · oversized rejected · type
errors (style/lyrics/seed/not-a-dict) · unicode payload · empty fields ·
CLI exit codes · matrix runner carries the RCA flags · the exact RC4
defect payload is pinned shape-wise.

`03_INPUT_TEST_MATRIX.csv` carries the executed matrix rows.
