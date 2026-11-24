#!/usr/bin/env python3
"""rc5_q3o_judge.py — Q3O (paper Control protocol) on a 48 GB ROCm GPU (RC5 M7).

What runs here is the OFFICIAL scorer code path with ONE substitution:

    vendor/wsb_q3o.PaperQ3OScorer.score(row)      -> executed verbatim
        frozen candidate weights (sha-checked), seed / sample / target binding,
        audio sha check, render_score_prompt, key worker (madmom, CPU),
        finish_judgement (native + traditional-key paper score), failure rules

    LocalVllmQwenJudge.judge_score(...)           -> replaced by Rc5HfQwenJudge

The replacement keeps everything the judge semantics depend on and changes
only the engine:
    same checkpoint (revision pinned by the bundle), same processor class,
    same chat template, same system/user prompts, same audio loading
    (qwen_omni_utils.process_mm_info), same greedy decoding (temperature 0,
    top_p 1, top_k -1), same max_tokens, same JSON parser;
    BF16 weights and BF16 compute, NO quantization; Thinker only (the Talker,
    Code2Wave and the vision tower take no part in a text judgement).
    Placement: attention/embeddings/lm_head/audio tower on the GPU, MoE
    experts of the first --gpu-layers layers on the GPU, the remaining
    experts on CPU through stock accelerate hooks (disclosed CPU offload).

This is therefore "Q3O full ROCm-adapted", not "official-equivalent": the
official judge is vLLM 0.14.0 + FlashAttention 2.8.3 on an 80 GB CUDA GPU.

Usage (inside the official metrics venv, see rc5_q3o_env notes):
  python scripts/rc5_q3o_judge.py --evaluator-root <ws>/benchmark/wsb_metrics \
      --rows rows.jsonl --out <dir> [--gpu-layers 16] [--limit N] [--ids a,b]
rows.jsonl: one official audio-manifest row per line (prepare_inputs output).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def object_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


# ----------------------------------------------------------------- judge
class Rc5HfQwenJudge:
    """Drop-in for eval_control.open_format_judge.LocalVllmQwenJudge.judge_score."""

    def __init__(self, evaluator_root: Path, config: dict, gpu_layers: int,
                 attn_implementation: str = "sdpa", log=print):
        import torch
        from qwen_omni_utils import process_mm_info
        from transformers import Qwen3OmniMoeProcessor
        self.torch = torch
        self.config = config
        self._process_mm_info = process_mm_info
        self._parse_json_object = _ofj_parse()
        self.root = evaluator_root
        self.log = log
        model_path = str(evaluator_root / json.loads(
            (evaluator_root / "configs/evaluation_assets.json").read_text())["models"]["q3o"]["path"])
        self.model_path = model_path
        t0 = time.time()
        self.processor = Qwen3OmniMoeProcessor.from_pretrained(model_path)
        log(f"[q3o-judge] processor loaded in {time.time()-t0:.1f}s")
        self.placement = self._load(model_path, gpu_layers, attn_implementation)

    # -- placement ---------------------------------------------------------
    def _device_map(self, model_path: str, gpu_layers: int) -> dict[str, str]:
        """One device per parameter-owning module of the Thinker-only model.

        Module names follow the checkpoint keys with the leading 'thinker.'
        stripped. The vision tower is not needed (no image input) and is sent
        to the 'disk' offload (memory-mapped, no RAM/VRAM cost)."""
        idx = json.load(open(Path(model_path) / "model.safetensors.index.json"))
        modules: dict[str, str] = {}
        for key in idx["weight_map"]:
            if not key.startswith("thinker."):
                continue
            name = key.rsplit(".", 1)[0]           # drop .weight / .bias
            name = name[len("thinker."):]
            parts = name.split(".")
            if parts[0] == "visual" or parts[0] == "model" and parts[1] == "visual":
                dev = "disk"
            elif parts[:2] == ["model", "layers"] and len(parts) > 4 and parts[4] == "experts":
                layer = int(parts[2])
                dev = 0 if layer < gpu_layers else "cpu"
            else:
                dev = 0
            modules[name] = dev
        return modules

    def _load(self, model_path: str, gpu_layers: int, attn_implementation: str) -> dict:
        import torch
        from transformers import Qwen3OmniMoeThinkerForConditionalGeneration
        device_map = self._device_map(model_path, gpu_layers)
        offload = Path(self.config.get("offload_dir", "/data/yue2/cache/q3o_offload"))
        offload.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        self.log(f"[q3o-judge] loading Thinker-only BF16: experts of layers 0..{gpu_layers-1} on GPU, "
                 f"layers {gpu_layers}..23 on CPU (accelerate hooks); vision tower offloaded to disk")
        model = Qwen3OmniMoeThinkerForConditionalGeneration.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True,
            device_map=device_map, offload_folder=str(offload), offload_state_dict=True,
            attn_implementation=attn_implementation)
        load_s = time.time() - t0
        model.eval()
        first = next(model.parameters())
        self.device = first.device
        counts: dict[str, int] = {}
        bytes_by_dev: dict[str, int] = {}
        for n, p in model.named_parameters():
            dev = str(p.device)
            counts[dev] = counts.get(dev, 0) + 1
            bytes_by_dev[dev] = bytes_by_dev.get(dev, 0) + p.numel() * p.element_size()
        placement = {"load_seconds": round(load_s, 1), "gpu_layers": gpu_layers,
                     "params_by_device": counts, "bytes_by_device": bytes_by_dev,
                     "attn_implementation": attn_implementation, "dtype": str(next(model.parameters()).dtype),
                     "transformers": __import__("transformers").__version__, "torch": torch.__version__,
                     "hip": torch.version.hip, "device_map_entries": len(device_map)}
        self.log(f"[q3o-judge] loaded in {load_s:.0f}s; bytes by device: "
                 + ", ".join(f"{k}={v/2**30:.2f}GiB" for k, v in bytes_by_dev.items()))
        self.model = model
        return placement

    # -- inference ---------------------------------------------------------
    def _generate_text(self, conversation: list, audio_path: Path, max_tokens: int) -> tuple[str, dict]:
        import torch
        prompt = self.processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True)
        audios, images, videos = self._process_mm_info(conversation, use_audio_in_video=False)
        if not audios:
            raise ValueError(f"failed to load audio: {audio_path}")
        inputs = self.processor(text=[prompt], audio=audios, images=images, videos=videos,
                                return_tensors="pt", padding=True, use_audio_in_video=False)
        meta = {"prompt_tokens": int(inputs["input_ids"].shape[1])}
        model = self.model
        target = self.device
        moved = {}
        for k, v in inputs.items():
            if hasattr(v, "to"):
                dt = torch.bfloat16 if v.is_floating_point() else None
                moved[k] = v.to(target, dtype=dt) if dt else v.to(target)
            else:
                moved[k] = v
        t0 = time.time()
        with torch.inference_mode():
            out = model.generate(**moved, do_sample=False, max_new_tokens=max_tokens,
                                 use_audio_in_video=False)
        gen_s = time.time() - t0
        n_in = moved["input_ids"].shape[1]
        cont = out[0][n_in:] if out.dim() == 2 else out.sequences[0][n_in:]
        n_tok = int(cont.shape[0])
        text = self.processor.batch_decode(cont[None], skip_special_tokens=True,
                                           clean_up_tokenization_spaces=False)[0]
        meta.update({"generated_tokens": n_tok, "generation_seconds": round(gen_s, 2),
                     "finish_reason": "length" if n_tok >= max_tokens else "stop",
                     "tokens_per_second": round(n_tok / gen_s, 2) if gen_s else None,
                     "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else None})
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        return text, meta

    def judge_score(self, item, *, system_prompt: str) -> dict:
        from eval_control.open_format_judge import _user_text
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        total_start = time.perf_counter()
        audio_path = Path(item.audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)
        audio_bytes = audio_path.stat().st_size
        user_text = _user_text(item)
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "audio", "audio": str(audio_path)},
                {"type": "text", "text": user_text}]},
        ]
        content_text, meta = self._generate_text(conversation, audio_path, int(self.config["max_tokens"]))
        total_seconds = time.perf_counter() - total_start
        judgement = self._parse_json_object(content_text)
        self.capture = [{"prompt": self.processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True),
                         "text": content_text, "generated_tokens": meta["generated_tokens"],
                         "finish_reason": meta["finish_reason"]}]
        return {
            **item.to_dict(),
            "provider": "rc5_hf_transformers_rocm",
            "judge_model": "Qwen/Qwen3-Omni-30B-A3B-Instruct@26291f793822fb6be9555850f06dfe95f2d7e695",
            "local_model_path": self.model_path,
            "request_format": "rc5-hf-thinker-bf16-mixed-placement",
            "audio_content_mode": "local_file",
            "timing": {"started_at": started_at,
                       "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "http_seconds": meta["generation_seconds"], "total_seconds": round(total_seconds, 3),
                       "payload_bytes": meta["prompt_tokens"], "response_bytes": len(content_text.encode("utf-8")),
                       "audio_bytes": audio_bytes, **{k: v for k, v in meta.items() if k != "generation_seconds"}},
            "judgement": judgement,
            "raw_response": {"text": content_text},
        }


def _ofj_parse():
    sys.path[:0] = [str(Path(os.environ["RC5_EVALUATOR_ROOT"]) / "src"),
                    str(Path(os.environ["RC5_EVALUATOR_ROOT"]) / "vendor")]
    from eval_control.open_format_judge import _parse_json_object
    return _parse_json_object


# ----------------------------------------------------------------- scorer
def build_official_scorer(evaluator_root: Path, judge, log=print):
    """PaperQ3OScorer with the official __init__ logic minus the vLLM engine.

    vendor/wsb_q3o.py is hash-pinned by the bundle (verify_release) and is not
    modified: its __init__ is re-implemented here line by line, keeping every
    check, and only the LocalVllmQwenJudge construction is replaced."""
    import wsb_q3o
    support = json.loads((evaluator_root / "configs/wsb_q3o_support.json").read_text())
    for name, checksum in support["runtime_sha256"].items():
        if sha_file(evaluator_root / name) != checksum:
            raise ValueError("Q3O runtime mismatch: " + name)
    config = json.loads((evaluator_root / "configs/evaluation.json").read_text())
    cfg = config["q3o"]
    required = support["q3o_config"]
    if config["seed"] != 1234 or any(cfg.get(k) != v for k, v in required.items()):
        raise ValueError("Paper Q3O configuration changed")
    assets = json.loads((evaluator_root / "configs/evaluation_assets.json").read_text())
    model = assets["models"]["q3o"]
    if model["revision"] != "26291f793822fb6be9555850f06dfe95f2d7e695":
        raise ValueError("Q3O revision mismatch")
    # bypass PaperQ3OScorer.__init__ (it constructs the CUDA vLLM judge and
    # asserts FlashAttention 2.8.3); then run its own loading code unchanged
    scorer = wsb_q3o.PaperQ3OScorer.__new__(wsb_q3o.PaperQ3OScorer)
    scorer.root = Path(evaluator_root)
    scorer.config = config
    scorer.support = support
    path = scorer.root / "data/wsb_q3o_candidate_weights.jsonl"
    if wsb_q3o.sha(path) != support["candidate_weights_sha256"]:
        raise ValueError("Frozen WSB weights changed")
    scorer.weights = {}
    for line in path.open():
        row = json.loads(line)
        pair = (row["prompt_index"], row["candidate_index"])
        if pair in scorer.weights:
            raise ValueError("Duplicate WSB weight identity")
        if object_hash(row["weight_judgement"]) != row["weight_sha256"]:
            raise ValueError("WSB weight content mismatch")
        scorer.weights[pair] = row
    if len(scorer.weights) != 1536:
        raise ValueError("Incomplete WSB candidate weight coverage")
    scorer.judge = judge
    scorer.audio_prompt = (scorer.root / "vendor/eval_control/prompts" / cfg["audio_prompt"]).read_text()
    scorer.capture = []
    return scorer, cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--rows", type=Path, required=True,
                    help="audio_manifest.jsonl rows (official prepare_inputs output)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gpu-layers", type=int, default=16)
    ap.add_argument("--attn", default="sdpa")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--dry-run", action="store_true", help="protocol checks only, no model")
    a = ap.parse_args()
    os.environ["RC5_EVALUATOR_ROOT"] = str(a.evaluator_root)
    sys.path[:0] = [str(a.evaluator_root / "src"), str(a.evaluator_root / "vendor"), str(a.evaluator_root)]
    import wsb_q3o  # noqa: E402  (frozen, hash-pinned)
    from eval_control.open_format_judge import OpenEvalItem  # noqa: E402
    a.out.mkdir(parents=True, exist_ok=True)
    log_f = open(a.out / "judge.log", "a")

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        log_f.write(line + "\n")
        log_f.flush()

    # protocol checks before anything expensive
    probe, cfg = build_official_scorer(a.evaluator_root, judge=None, log=log)
    log("[q3o-judge] official protocol checks passed (frozen weights, config, runtime hashes, revision)")
    if a.dry_run:
        return 0
    judge = Rc5HfQwenJudge(a.evaluator_root, cfg, a.gpu_layers, a.attn, log=log)
    scorer, cfg = build_official_scorer(a.evaluator_root, judge=judge, log=log)
    (a.out / "runtime_receipt.json").write_text(json.dumps({
        "schema": "yue2-rc5-q3o-runtime/1", "judge": "Rc5HfQwenJudge (Thinker-only BF16, accelerate mixed placement)",
        "placement": judge.placement, "q3o_config": cfg,
        "official_engine": "vLLM 0.14.0 + flash-attn 2.8.3 on an 80 GB CUDA GPU (NOT used here)",
        "equivalence": "NOT established: same weights/prompts/decoding/precision, different engine and attention kernels",
        "evaluator_bundle_sha256": sha_file(a.evaluator_root / "release.json")}, indent=1, default=str) + "\n")
    rows = [json.loads(l) for l in a.rows.read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: (r["prompt_index"], r["candidate_index"]))
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    if a.limit:
        rows = rows[:a.limit]
    results, failed = [], 0
    for n, row in enumerate(rows, 1):
        dest = a.out / "receipts" / row["id"] / "q3o.json"
        if dest.is_file():
            prev = json.loads(dest.read_text())
            if prev.get("status") in ("complete", "not_applicable"):
                results.append(prev)
                continue
        t0 = time.time()
        try:
            res = scorer.score(row)          # official code path
        except Exception as exc:  # noqa: BLE001 - recorded, never hidden
            res = {"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc(), "raw_decode": scorer.capture}
        res["seconds"] = round(time.time() - t0, 2)
        res["judge_provider"] = "rc5_hf_transformers_rocm"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
        results.append(res)
        failed += res["status"] == "failed"
        score = (res.get("scores") or {}).get("q3o")
        log(f"{n}/{len(rows)} {row['id']}: {res['status']} q3o={score} "
            f"tokens={((res.get('raw_decode') or [{}])[-1]).get('generated_tokens')} "
            f"{res['seconds']}s {('ERR ' + res['error'][:100]) if res['status'] == 'failed' else ''}")
    done = [r for r in results if r["status"] == "complete" and (r.get("scores") or {}).get("q3o") is not None]
    summary = {
        "schema": "yue2-rc5-q3o-run-summary/1",
        "protocol": "WSB-paper-Control-20260905-frozen-candidate-weights (frozen weights, traditional-key MIREX override, 0-5)",
        "judge_provider": "rc5_hf_transformers_rocm (ROCm-adapted; official vLLM/CUDA judge not used)",
        "rows": len(rows), "complete": sum(1 for r in results if r["status"] == "complete"),
        "not_applicable": sum(1 for r in results if r["status"] == "not_applicable"),
        "failed": failed,
        "scored": len(done),
        "q3o_mean_0_5": round(sum(r["scores"]["q3o"] for r in done) / len(done), 6) if done else None,
        "mean_seconds": round(sum(r.get("seconds", 0) for r in results) / max(1, len(results)), 2),
        "ids": [r.get("id") for r in results],
        "status": "COMPLETE" if done and not failed else ("COMPLETE_WITH_NOT_APPLICABLE" if not failed else "FAILED_ROWS"),
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    log(json.dumps({k: summary[k] for k in ("rows", "complete", "not_applicable", "failed", "scored", "q3o_mean_0_5")}))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
