# Reviewer B — ROCm HTTP E2E Integrity (independent subagent, 2026-10-13)

Scope: verify genuine Omni source, genuine W7900 execution, genuine HTTP WAV response, path claims.

## Verdict: **HTTP_E2E_REVIEW: PASS** (zero P0/P1)

Independently verified:
- Decoded both bodies with soundfile: 48,000 Hz, 2 ch, finite, 20.479 s / 47.239 s, RMS 0.0860 / 0.1470. Recomputed SHA256 `358ffc66…2feed` / `218634d4…26bd` match evidence bit-for-bit. Byte math exact: frames×4+44 = content-length = file size.
- Genuine RIFF/WAVE PCM 16-bit headers; not JSON error bodies; not recycled from WSB archive (no identical files).
- HTTP/1.1 200, content-type audio/wav, x-request-ids match server.log.
- server.log: preprocessing/synth-done lines verbatim (982,976 and 2,267,456 samples; elapsed 15.25 s / 38.11 s); placement GPU 0 'AMD Radeon Pro W7900D' 47.98 GiB.
- GPU trace: util 0→100% (99–100%) exactly bracketing the full-config request window; VRAM 21→35%.
- Source identity: repo HEAD 50c91c08…, worktree clean; sglang_omni → repo checkout; sglang → pristine sglang-src (ccae40c, empty diff) via the server's own interpreter.
- Waveforms distinct (lengths differ, max|Δ|=0.970, corr=0.40) — not cached despite identical seed (different token budgets/ode_steps).
- Code gates confirmed: song.py:41-56 step graph off on ROCm (looped reference AR); fa3.py:31-33 skips shared FA3 op → torch.ops.aten._flash_attention_forward (native ATen varlen); fastpath.py:75 fast sampler off (DeepSelect disabled).
- No CUDA execution claimed or present: torch.version.cuda None, HIP 7.14.60850; "cuda" strings are PyTorch HIP aliasing.

Findings:
- P2 (fixed during review cycle): smoke_response.json request_wall_s corrected 30→15 s to match client.log.
- P2 (documented limitation): gpu_trace.log covers only the full-config window; smoke-window util is inferential (same server/GPU, synth elapsed 15.25 s in server.log). No fabrication indicators found.
