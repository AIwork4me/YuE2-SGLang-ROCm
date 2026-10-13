# Phase 6 — Independent Packaging Review: python-multipart declaration

Commit: daf1a113 on fix/declare-python-multipart (base 85ae4b73). Reviewer independently reproduced all claims in /tmp/opencode/pkgtest-venv (fastapi 0.143.0, starlette 1.8.0, uvicorn 0.54.0).

## Verification results

1. **Unconditional registration — CONFIRMED.** `register_voices(app)` is called unconditionally at `sglang_omni/serve/openai_api.py:327` inside `create_app`; `POST /v1/audio/voices` with `UploadFile = File(...)`/`Form(...)` at lines 363-369. `supports_uploaded_voice_references` only feeds `SpeechRequestValidator` (line 305), never route registration. Only `register_realtime` is conditional (line 334). `speech_to_text.py` `parse_speech_to_text_form` declares further File/Form params.
2. **No serve bypass — CONFIRMED.** `sgl-omni` → `sglang_omni.cli:app` → `cli/serve.py:468` → `launcher.py:518 create_app`; the `sglang.serve_backends` entry point also targets `create_app`. All paths hit it.
3. **Floor sanity — OK.** PyPI check succeeded: 0.0.20 exists (line: ...0.0.20, 0.0.19...0.0.32). 0.0.9 fixed CVE-2024-24762; `>=0.0.20` is a valid, conservative maintained-line floor.
4. **Not transitively redundant everywhere.** gradio (which requires python-multipart) is a *main* dependency only in base `pyproject.toml:91`, `pyproject_musa.toml:64`, `pyproject_rocm.toml:70` — absent from cpu/npu/xpu. fastapi itself does not depend on it (proven by isolated venv). Declaration is strictly necessary for cpu/npu/xpu and correct best-practice elsewhere.
5. **Test quality — CONFIRMED by reproduction.** Uninstalled python-multipart in pkgtest-venv: `test_form_file_route_registers_at_startup` FAILED with exact `RuntimeError: Form data requires "python-multipart"`; declaration test still passed. Reinstalled 0.0.32 (state restored, verified): 2/2 pass.
6. **All 6 variants covered; no missed install path.** All pyproject*.toml valid TOML, each declares python-multipart once. Every docker/install path resolves deps from a pyproject variant: base Dockerfile `-r pyproject.toml`, rocm/cpu `-r pyproject_rocm/cpu.toml` + `--no-deps -e .`, musa/xpu `pip install -e .`/`pip install .`, install.sh `uv pip install -e "$PROJECT_SPEC"`. npu.Dockerfile only freezes metadata. No separate pip lists omit it.

## Findings
- **P0:** none.
- **P1:** none.
- **P2:** none.
- **P3-1:** In base/musa/rocm, gradio (main dep) already pulls python-multipart transitively; declaration redundant there but correct (direct use ⇒ direct declaration) — no action.
- **P3-2:** `test_python_multipart_declared_wherever_fastapi_is_declared` uses substring match ("fastapi" in text), which could match a comment; trivially robust enough as-is.
- **P3-3:** Startup test reproduces a minimal File/Form route rather than importing `create_app` (avoids heavy model imports) — reasonable trade-off, still fails exactly when the dep is missing.

## PHASE6_VERDICT: PASS

Fix is necessary (startup failure on cpu/npu/xpu without it), correct (right package, valid `>=0.0.20` floor, all 6 variants, tests genuinely gate the regression), and minimal (+1 line × 6 + 1 focused test file, 58 insertions, no unrelated churn).
