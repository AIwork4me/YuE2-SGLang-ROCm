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
# expandable segments avoid fragmentation OOM when the 48 GB card repeatedly
# frees ~1.2 GiB layer originals and allocates ~1.2 GiB packed stacks
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")


def cpu_quota() -> int:
    """CPUs this container may actually use (cgroup cpu.max), not os.cpu_count().

    The bench exposes 128 logical CPUs but grants a quota of 16: torch's
    default intra-op pool (one thread per visible CPU) thrashes inside the
    quota and makes small CPU matmuls ~100x slower (measured prefill 532 s)."""
    try:
        q, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if q != "max":
            return max(1, int(int(q) / int(period)))
    except (OSError, ValueError):
        pass
    return max(1, len(os.sched_getaffinity(0)))


def configure_cpu_threads():
    import torch
    n = cpu_quota()
    torch.set_num_threads(n)
    return n


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

    THINKER_EOS_TOKEN_ID = 151645      # <|im_end|>: official HF thinker_eos_token_id default

    def __init__(self, evaluator_root: Path, config: dict, gpu_layers: int,
                 attn_implementation: str = "sdpa", log=print):
        # librosa (and madmom) ship lazy_loader submodules whose numba
        # stencil/guvectorize compilation SEGFAULTS (rc=139 inside llvmlite
        # opt passes) once torch's HIP stack is loaded in this process.
        # Force the whole compile chain NOW, torch-free: attribute access on
        # a real librosa.load() executes librosa.core.audio (eager module
        # level ufuncs) and every lazily-imported submodule it needs.
        import io
        t_warm = time.time()
        import numpy as _np
        import soundfile as _sf
        _buf = io.BytesIO()
        _sf.write(_buf, _np.zeros(1600, dtype="float32"), 16000, format="WAV")
        _buf.seek(0)
        import librosa
        librosa.load(_buf, sr=16000)          # executes the lazy submodule chain
        librosa.resample(_np.zeros(1600, dtype="float32"), orig_sr=16000, target_sr=24000)
        try:                                   # official key worker dependency
            import madmom  # noqa: F401  (on the evaluator's sys.path, not yet here)
        except ImportError:
            pass
        log(f"[q3o-judge] librosa/madmom numba warmed in {time.time()-t_warm:.1f}s "
            "(torch-free, before model load)")
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
        # The official judge wraps ``llm.generate`` so that every call appends
        # {prompt, text, generated_tokens, finish_reason} to ``scorer.capture``;
        # ``PaperQ3OScorer.score()`` resets that list per song and fails a song
        # when any record has finish_reason == 'length'. The adapter must feed
        # the scorer's list (not its own) or truncated judgements would pass.
        self.scorer = None
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
        placement["moe_placement"] = self._install_moe_blocks(model, device_map, gpu_layers)
        self.model = model
        placement["device_audit"] = self._audit_and_fix_devices(model, device_map)
        return placement

    def _install_moe_blocks(self, model, device_map: dict, gpu_layers: int) -> dict:
        """Place the 48 MoE layers of the Thinker (scripts/rc5_q3o_moe.py).

        * layers < gpu_layers: experts stay on the GPU, replaced by a batched
          block (two bmm per layer, no host loop) — the plain HF loop costs
          about nine GPU->CPU synchronisations per layer (0.21 s/token).
        * layers >= gpu_layers: accelerate maps device_map["cpu"] to "weights
          in host RAM, streamed to the GPU for every forward" (~1 GB of expert
          weights per decoded token); they are restored to the CPU and replaced
          by a CPU-resident block (fp32 compute, official bf16 rounding points).
        Both blocks are checked against the verbatim HF loop in
        tests/test_rc5_q3o_moe.py."""
        import torch
        from accelerate.hooks import remove_hook_from_module
        from accelerate.utils import set_module_tensor_to_device
        from pathlib import Path as _P
        import importlib.util as _iu
        _spec = _iu.spec_from_file_location("rc5_q3o_moe", _P(__file__).with_name("rc5_q3o_moe.py"))
        _mod = _iu.module_from_spec(_spec)
        sys.modules["rc5_q3o_moe"] = _mod          # importable by the run loop (tie stats)
        _spec.loader.exec_module(_mod)
        threads = configure_cpu_threads()
        self.log(f"[q3o-judge] CPU intra-op threads set to {threads} (cgroup quota)")
        cpu_leaves = [n for n, d in device_map.items() if d == "cpu"]
        restored, failures = 0, []
        for name in cpu_leaves:
            mod = model.get_submodule(name)
            hook = getattr(mod, "_hf_hook", None)
            wm = getattr(hook, "weights_map", None) if hook is not None else None
            for pn, _p in mod.named_parameters(recurse=False):
                value = wm[pn] if wm is not None else None
                if value is None or value.is_meta:
                    failures.append(f"{name}.{pn}")
                    continue
                set_module_tensor_to_device(mod, pn, torch.device("cpu"), value=value)
                restored += 1
            remove_hook_from_module(mod, recurse=False)
        if failures:
            raise RuntimeError(f"{len(failures)} CPU-mapped weights had no value in the "
                               f"weights_map, e.g. {failures[:5]}")
        # release the host copies accelerate still references BEFORE packing,
        # so each layer's old weights are freed as soon as it is replaced
        released = 0
        for m in model.modules():
            h = getattr(m, "_hf_hook", None)
            if h is not None and getattr(h, "weights_map", None) is not None:
                h.weights_map = None
                released += 1
        layers = model.model.layers
        n_layers = len(layers)
        gpu_idx, cpu_idx = [], []
        for idx in range(n_layers):
            block = layers[idx].mlp
            if os.environ.get("RC5_Q3O_PACK_DEBUG") and idx % 4 == 0 and torch.cuda.is_available():
                import gc as _gc
                self.log(f"[pack-debug] layer {idx}: allocated="
                         f"{torch.cuda.memory_allocated()/2**30:.2f}GiB reserved="
                         f"{torch.cuda.memory_reserved()/2**30:.2f}GiB gc_tracked="
                         f"{len(_gc.get_objects())}")
            if idx < gpu_layers:
                gpu_moe_mode = os.environ.get("RC5_Q3O_GPU_MOE", "stable-loop")
                if gpu_moe_mode == "batched":
                    layers[idx].mlp = _mod.BatchedGpuMoeBlock(block, free_source=True)
                else:
                    # validated 48 GB path: stock HF bf16 experts, forward
                    # patched in place for the deterministic tie-break; no
                    # packing (the batched block's buffers do not fit —
                    # measured, see install_stable_topk_gpu_moe)
                    _mod.install_stable_topk_gpu_moe(block)
                gpu_idx.append(idx)
                del block
                if torch.cuda.is_available():
                    import gc
                    gc.collect()
                    torch.cuda.empty_cache()
            else:
                layers[idx].mlp = _mod.CpuResidentMoeBlock(block, log=self.log)
                cpu_idx.append(idx)
                del block
        self._moe_modules = [layers[i].mlp for i in range(n_layers)]
        return {"mode": (f"{'batched-GPU MoE' if os.environ.get('RC5_Q3O_GPU_MOE') == 'batched' else 'stock HF GPU MoE + stable tie-break'} "
                         "(< gpu_layers) + CPU-resident MoE (>= gpu_layers), scripts/rc5_q3o_moe.py; "
                         "official rounding points kept"),
                "gpu_moe_mode": os.environ.get("RC5_Q3O_GPU_MOE", "stable-loop"),
                "cpu_leaf_modules": len(cpu_leaves), "weights_restored_to_cpu": restored,
                "gpu_moe_layers": gpu_idx, "cpu_moe_layers": cpu_idx, "layers_total": n_layers,
                "weights_map_references_released": released, "cpu_threads": threads}

    def _audit_and_fix_devices(self, model, device_map: dict) -> dict:
        """Make the placement TRUE before anything runs.

        1. Non-persistent buffers are not in the checkpoint and are not covered
           by a parameter-derived device map (the audio tower's sinusoidal
           `positional_embedding` stayed on CPU -> 'Expected all tensors to be
           on the same device, cuda:0 and cpu' in the first real attempt).
           Buffers of GPU-resident sections are moved to the GPU explicitly.
        2. Fail loud if any weight outside the disk-offloaded vision tower is
           still on the meta device (i.e. was never materialised)."""
        # accelerate >= 1.10 (verified 1.12.0): when an offload folder is in
        # play, modules mapped to "cpu" are ALSO offloaded through a
        # weights_map: their parameters sit on the meta device and a hook
        # installs the real weights (held in host RAM) for the duration of
        # each forward. "meta" therefore does NOT mean "never loaded". What
        # must be true is: every meta parameter outside the disk-offloaded
        # vision tower has an accelerate offload hook, and such a module
        # really computes with its weights (checked once on a real module).
        audit: dict = {"buffers_moved": 0, "meta_without_hook": 0,
                       "cpu_offloaded_via_weights_map": 0, "by_section": {}}
        model_root = model.model if hasattr(model, "model") else model
        visual_prefix = "model.visual." if hasattr(model_root, "visual") else "visual."
        sections: dict[tuple, dict] = {}
        sample_cpu_module = None
        for name, module in model.named_modules():
            params = list(module.parameters(recurse=False))
            if not params:
                continue
            dev = str(params[0].device)
            if dev == "meta":
                if name.startswith(visual_prefix):
                    continue                      # disk-offloaded, never used (no image input)
                hook = getattr(module, "_hf_hook", None)
                if hook is not None and getattr(hook, "offload", False) \
                        and getattr(hook, "weights_map", None) is not None:
                    audit["cpu_offloaded_via_weights_map"] += len(params)
                else:
                    audit["meta_without_hook"] += len(params)
                if sample_cpu_module is None and name.endswith("down_proj"):
                    sample_cpu_module = (name, module)
        probe_mlp = next((m for m in getattr(self, "_moe_modules", [])
                         if type(m).__name__ == "CpuResidentMoeBlock"), None)
        for name, param in model.named_parameters():
            sec = "visual" if name.startswith(visual_prefix) else (
                "experts" if ".mlp.experts." in name else ("audio_tower" if name.startswith("audio_tower.")
                                                           else "dense"))
            layer = int(name.split(".layers.")[1].split(".")[0]) if ".layers." in name else None
            key = (sec, layer)
            d = sections.setdefault(key, {"n": 0, "bytes": 0, "devices": set()})
            d["n"] += 1
            d["bytes"] += param.numel() * param.element_size()
            d["devices"].add(str(param.device))
        audit["by_section"] = {f"{k[0]}{'' if k[1] is None else '[%d]' % k[1]}":
                               {"n": v["n"], "GiB": round(v["bytes"] / 2**30, 3),
                                "devices": sorted(v["devices"])} for k, v in sorted(
                                   sections.items(), key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1))}
        audit["layers_total"] = getattr(model_root.config, "num_hidden_layers", None) if hasattr(model_root, "config") else None
        if audit["meta_without_hook"]:
            raise RuntimeError(f"{audit['meta_without_hook']} weights are on the meta device without an "
                               f"offload hook (never materialised): {json.dumps(audit['by_section'])[:2500]}")
        if probe_mlp is not None:
            import torch
            seen = {}
            try:
                with torch.no_grad():
                    inp = torch.ones(1, 4, int(probe_mlp.gate_w.shape[1]), device=self.device,
                                     dtype=torch.bfloat16)
                    out, logits = probe_mlp(inp)
                seen.update(out_device=str(out.device), out_dtype=str(out.dtype),
                            out_finite=bool(torch.isfinite(out).all()),
                            out_abs_sum=float(out.float().abs().sum()),
                            logits_device=str(logits.device), logits_dtype=str(logits.dtype),
                            weight_gib=round((probe_mlp.gate_up[0].numel() + probe_mlp.down[0].numel())
                                             * 4 * probe_mlp.num_experts / 2**30, 3))
            except Exception as exc:  # noqa: BLE001 - recorded, raised below
                seen["error"] = f"{type(exc).__name__}: {exc}"
            # behavioural proof that the CPU-resident block computes with the
            # real weights: a ones-input must give a finite, non-zero output
            audit["cpu_resident_smoke"] = seen
            if "error" in seen or not seen.get("out_finite", False) \
                    or not seen.get("out_abs_sum", 0.0) > 0.0:
                raise RuntimeError(f"CPU-resident MoE block did not compute with real weights: "
                                   f"{json.dumps(seen)}")
        moved = []
        for name, buf in model.named_buffers():
            sec = "visual" if name.startswith(visual_prefix) else None
            if sec == "visual" or str(buf.device) == self.device:
                continue
            # buffers belong to GPU-resident sections (experts layers on CPU have none)
            if ".mlp.experts." in name and device_map.get(name.rsplit(".", 2)[0] if name.count(".") >= 2 else "", 0) == "cpu":
                continue
            parts = name.split(".")
            owner = ".".join(parts[:-1])
            target = device_map.get(owner)
            if target is None:
                # nearest mapped ancestor; `audio_tower` itself owns no
                # parameter, so also fall back to its mapped descendants
                for i in range(len(parts) - 2, 0, -1):
                    target = device_map.get(".".join(parts[:i]))
                    if target is not None:
                        break
            if target is None:
                subs = [v for k, v in device_map.items() if k.startswith(owner + ".")]
                if subs:
                    target = subs[0]
            if target is None or (target not in ("cpu", "disk") and not isinstance(target, str)):
                target = 0                      # GPU-resident section by default
            if target == 0 and buf.device.type != "cuda":
                moved.append((name, str(buf.device)))
        # perform the moves on the module tree (buffers are replaced in place)
        for name, _src in moved:
            module_name, buf_name = name.rsplit(".", 1) if "." in name else ("", name)
            mod = model.get_submodule(module_name) if module_name else model
            setattr(mod, buf_name, getattr(mod, buf_name).to(self.device))
        audit["buffers_moved"] = len(moved)
        audit["buffers_moved_names"] = [n for n, _ in moved][:20]
        return audit

    # -- inference ---------------------------------------------------------
    def _generate_text(self, conversation: list, audio_path: Path, max_tokens: int) -> tuple[str, dict]:
        import torch
        prompt = self.processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True)
        audios, images, videos = self._process_mm_info(conversation, use_audio_in_video=False)
        if not audios:
            raise ValueError(f"failed to load audio: {audio_path}")
        inputs = self.processor(text=[prompt], audio=audios, images=images, videos=videos,
                                return_tensors="pt", padding=True, use_audio_in_video=False)
        meta = {"prompt_tokens": int(inputs["input_ids"].shape[1]), "prompt": prompt}
        model = self.model
        target = self.device
        marks = {}

        class _Timer(torch.nn.Module):     # logits processor: marks prefill / decode boundary
            def __call__(self, input_ids, scores):
                now = time.time()
                marks.setdefault("steps", 0)
                marks["steps"] += 1
                marks.setdefault("t_step1", now)
                marks["t_last"] = now
                return scores
        moved = {}
        for k, v in inputs.items():
            if hasattr(v, "to"):
                dt = torch.bfloat16 if v.is_floating_point() else None
                moved[k] = v.to(target, dtype=dt) if dt else v.to(target)
            else:
                moved[k] = v
        t0 = time.time()
        with torch.inference_mode():
            # The checkpoint's generation_config.json carries only talker
            # settings (eos_token_id=None), so generation would never stop.
            # The official HF entry point passes thinker_eos_token_id=151645;
            # vLLM stops on the same model EOS.
            out = model.generate(**moved, do_sample=False, max_new_tokens=max_tokens,
                                 use_audio_in_video=False, logits_processor=[_Timer()],
                                 eos_token_id=self.THINKER_EOS_TOKEN_ID)
        gen_s = time.time() - t0
        steps = marks.get("steps", 0)
        if steps > 1:
            meta["prefill_seconds"] = round(marks["t_step1"] - t0, 2)
            meta["decode_seconds"] = round(marks["t_last"] - marks["t_step1"], 2)
            meta["decode_seconds_per_token"] = round((marks["t_last"] - marks["t_step1"]) / (steps - 1), 4)
        n_in = moved["input_ids"].shape[1]
        cont = out[0][n_in:] if out.dim() == 2 else out.sequences[0][n_in:]
        n_tok = int(cont.shape[0])
        meta["generated_token_ids_sha256"] = hashlib.sha256(
            json.dumps(cont.tolist()).encode()).hexdigest()
        meta["input_ids_sha256"] = hashlib.sha256(
            json.dumps(moved["input_ids"][0].tolist()).encode()).hexdigest()
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
        record = {"prompt": meta["prompt"], "text": content_text,
                  "generated_tokens": meta["generated_tokens"],
                  "finish_reason": meta["finish_reason"],
                  "generated_token_ids_sha256": meta.get("generated_token_ids_sha256"),
                  "input_ids_sha256": meta.get("input_ids_sha256")}
        self.capture = [record]
        if self.scorer is not None:
            self.scorer.capture.append(record)      # official record() semantics
        self.log(f"[q3o-judge]   prompt_tokens={meta['prompt_tokens']} generated={meta['generated_tokens']} "
            f"({meta['finish_reason']}) prefill={meta.get('prefill_seconds')}s "
                        f"decode={meta.get('decode_seconds')}s ({meta.get('decode_seconds_per_token')} s/token) "
                        f"peak_vram={round((meta.get('peak_vram_bytes') or 0) / 2**30, 2)}GiB")
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
                       "audio_bytes": audio_bytes,
                       **{k: v for k, v in meta.items() if k not in ("generation_seconds", "prompt")}},
            "judgement": judgement,
            "raw_response": {"text": content_text},
        }


def _proc_resources() -> dict:
    """Peak host memory of this process and VRAM of the device (disclosed
    CPU offload)."""
    out = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmHWM:", "VmRSS:")):
                out["host_" + line.split(":")[0].lower() + "_bytes"] = int(line.split()[1]) * 1024
    except OSError:
        pass
    try:
        import torch
        out["peak_vram_bytes"] = int(torch.cuda.max_memory_allocated())
    except Exception:  # noqa: BLE001
        pass
    return out


# ------------------------------------------------- resume identity (P0.3.2)
def atomic_write_json(path: Path, obj) -> None:
    """No-clobber-tolerant atomic publish: a crash can never leave a torn
    receipt, and a serialisation failure never damages an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, path)


def receipt_reusable(prev: dict, identity_sha: str, audio_sha: str) -> tuple[bool, str]:
    """A previous receipt may only be reused when the WHOLE judge identity
    (code, model, prompts, decoding, placement, tie-break) AND the audio
    bytes match the current run. Anything else is re-scored; the old file is
    preserved under a superseded- name, never overwritten in place."""
    if prev.get("status") not in ("complete", "not_applicable"):
        return False, f"status_{prev.get('status')}"
    if prev.get("identity_sha256") != identity_sha:
        return False, "judge_identity_mismatch"
    if prev.get("audio_sha256") != audio_sha:
        return False, "audio_mismatch"
    return True, "reusable"


def identity_drift(prev: dict, cur: dict) -> dict:
    """Frozen-key comparison of two run identities (every field must match:
    there is no per-session field here because a judge process is stateless
    apart from its configuration)."""
    keys = set(prev) | set(cur)
    return {k: (prev.get(k), cur.get(k)) for k in sorted(keys)
            if k not in ("created_at_utc",) and prev.get(k) != cur.get(k)}


def compute_run_identity(evaluator_root: Path, cfg: dict, gpu_layers: int, attn: str,
                         cpu_threads: int, torch_ver: str, hip, transformers_ver,
                         log=print) -> dict:
    """Everything a Q3O receipt's meaning depends on. Model weights are
    content-hashed (all safetensors shards + configs): a re-download, a
    silent cache change or a revision move can never reuse old receipts."""
    import glob
    model_path = str(evaluator_root / json.loads(
        (evaluator_root / "configs/evaluation_assets.json").read_text())["models"]["q3o"]["path"])
    t0 = time.time()
    shard_hashes = {}
    for p in sorted(glob.glob(f"{model_path}/*.safetensors")):
        shard_hashes[Path(p).name] = sha_file(Path(p))
    config_hashes = {n: sha_file(Path(model_path) / n) for n in
                     ("config.json", "generation_config.json", "chat_template.json",
                      "preprocessor_config.json", "tokenizer_config.json", "vocab.json",
                      "merges.txt")}
    log(f"[q3o-judge] model content-hashed in {time.time()-t0:.0f}s "
        f"({len(shard_hashes)} shards + {len(config_hashes)} config files)")
    support = json.loads((evaluator_root / "configs/wsb_q3o_support.json").read_text())
    prompts = {
        "audio_prompt": sha_file(evaluator_root / "vendor/eval_control/prompts" / cfg["audio_prompt"]),
        "weight_prompt": sha_file(evaluator_root / "vendor/eval_control/prompts" / cfg["weight_prompt"]),
    }
    ident = {
        "schema": "yue2-rc5-q3o-identity/2",
        "judge_source_sha256": sha_file(Path(__file__)),
        "moe_source_sha256": sha_file(Path(__file__).with_name("rc5_q3o_moe.py")),
        "evaluator_release_sha256": sha_file(evaluator_root / "release.json"),
        "evaluator_runtime_sha256": support["runtime_sha256"],
        "model_revision": json.loads((evaluator_root / "configs/evaluation_assets.json")
                                     .read_text())["models"]["q3o"]["revision"],
        "model_shard_sha256": shard_hashes,
        "model_config_sha256": config_hashes,
        "prompt_sha256": prompts,
        "q3o_config_sha256": object_hash(cfg),
        "decoding_config_sha256": object_hash({
            "do_sample": False, "temperature": cfg["temperature"], "top_p": cfg["top_p"],
            "top_k": cfg["top_k"], "max_tokens": cfg["max_tokens"],
            "eos_token_id": Rc5HfQwenJudge.THINKER_EOS_TOKEN_ID, "seed": 1234}),
        "precision": "bfloat16 (Thinker-only, no quantisation)",
        "attention_backend": attn,
        "torch_version": torch_ver, "hip": hip, "transformers_version": transformers_ver,
        "placement_config": {"gpu_layers": gpu_layers, "cpu_threads": cpu_threads,
                             "mode": "BatchedGpuMoeBlock(<gpu_layers) + CpuResidentMoeBlock(>=gpu_layers)"},
        "tie_break_policy": "lowest_expert_index (stable argsort of fp32 softmax of bf16 router logits)",
        "equivalence_claim": "NONE: ROCm-adapted judge; official engine is vLLM 0.14.0 + FlashAttention 2.8.3 on CUDA",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # RC6.1 M4 fix: created_at_utc is EXECUTION PROVENANCE, not scientific
    # content — a timestamp in the hash made every same-configuration run a
    # "different judge identity", correctly refusing reuse but for a
    # non-scientific reason. The canonical hash covers content only; the
    # timestamp stays in the receipt as provenance.
    ident["identity_sha256"] = object_hash(
        {k: v for k, v in ident.items()
         if k not in ("identity_sha256", "created_at_utc")})
    return ident


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
    if judge is not None:
        judge.scorer = scorer                   # feed the scorer's capture list
    return scorer, cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--rows", type=Path, required=True,
                    help="audio_manifest.jsonl rows (official prepare_inputs output)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gpu-layers", type=int, default=34,
                    help="layers whose MoE experts stay on the GPU (48 layers x 1.125 GiB each); the rest are "
                         "CPU-offloaded through accelerate's weights_map")
    ap.add_argument("--attn", default="sdpa")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--repeat", type=int, default=1,
                    help="score each row N times (repeatability measurement); every run is "
                         "kept as receipts/<id>/q3o.run-K.json, the last also as q3o.json")
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
    identity = compute_run_identity(
        a.evaluator_root, cfg, a.gpu_layers, a.attn,
        judge.placement["moe_placement"]["cpu_threads"],
        judge.placement["torch"], judge.placement["hip"],
        judge.placement["transformers"], log=log)
    # different judge configuration => different run directory, always
    ident_path = a.out / "identity.json"
    if ident_path.is_file():
        prev_ident = json.loads(ident_path.read_text())
        drift = identity_drift(prev_ident, identity)
        if drift:
            log("FATAL: this output directory belongs to a DIFFERENT judge identity "
                "(never mix configurations in one run):")
            for k in sorted(drift):
                log(f"   {k}: {str(drift[k][0])[:90]} -> {str(drift[k][1])[:90]}")
            return 3
        log("[q3o-judge] resume: output directory identity matches this judge exactly")
    else:
        atomic_write_json(ident_path, identity)
        log(f"[q3o-judge] run identity {identity['identity_sha256'][:16]} written")
    atomic_write_json(a.out / "runtime_receipt.json", {
        "schema": "yue2-rc5-q3o-runtime/2", "judge": "Rc5HfQwenJudge (Thinker-only BF16, accelerate mixed placement)",
        "placement": judge.placement, "q3o_config": cfg,
        "identity_sha256": identity["identity_sha256"],
        "official_engine": "vLLM 0.14.0 + flash-attn 2.8.3 on an 80 GB CUDA GPU (NOT used here)",
        "equivalence": "NOT established: same weights/prompts/decoding/precision, different engine and attention kernels",
        "evaluator_bundle_sha256": sha_file(a.evaluator_root / "release.json")})
    rows = [json.loads(l) for l in a.rows.read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: (r["prompt_index"], r["candidate_index"]))
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    if a.limit:
        rows = rows[:a.limit]
    results, failed = [], 0
    audio_sha_cache: dict[str, str] = {}
    reused, rescored, superseded = 0, 0, 0
    for n, row in enumerate(rows, 1):
        rid = row.get("id") or f"p{row.get('prompt_index')}_c{row.get('candidate_index')}"
        dest = a.out / "receipts" / rid / "q3o.json"
        audio_path = Path(row["audio_path"]) if row.get("audio_path") else None
        if audio_path is None:
            for key in ("path", "audio", "flac_path"):
                if row.get(key):
                    audio_path = Path(row[key])
                    break
        audio_sha = audio_sha_cache.get(str(audio_path))
        if audio_sha is None and audio_path is not None and audio_path.is_file():
            audio_sha = sha_file(audio_path)
            audio_sha_cache[str(audio_path)] = audio_sha
        declared = row.get("audio_sha256")
        if declared and audio_sha and declared != audio_sha:
            log(f"FATAL: {rid}: audio bytes changed since prepare_inputs "
                f"(declared {str(declared)[:16]}, measured {audio_sha[:16]})")
            return 3
        if dest.is_file() and a.repeat == 1:
            try:
                prev = json.loads(dest.read_text())
            except ValueError:
                prev = {}
            ok, why = receipt_reusable(prev, identity["identity_sha256"], audio_sha or "")
            if ok:
                results.append(prev)
                reused += 1
                log(f"{n}/{len(rows)} {rid}: reuse ({why}) "
                    f"q3o={(prev.get('scores') or {}).get('q3o')}")
                continue
            keep = dest.with_name(f"q3o.superseded-{time.strftime('%Y%m%dT%H%M%SZ')}-{why}.json")
            os.replace(dest, keep)          # preserved, never overwritten
            superseded += 1
            log(f"{n}/{len(rows)} {rid}: previous receipt NOT reusable ({why}); "
                f"preserved as {keep.name}; re-scoring")
        runs = []
        for rep in range(1, max(1, a.repeat) + 1):
            import rc5_q3o_moe as _moe
            _moe.reset_tie_stats()
            t0 = time.time()
            try:
                res = scorer.score(row)      # official code path
            except Exception as exc:  # noqa: BLE001 - recorded, never hidden
                res = {"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc(), "raw_decode": list(scorer.capture or [])}
            res["seconds"] = round(time.time() - t0, 2)
            res["judge_provider"] = "rc5_hf_transformers_rocm"
            res["resources"] = _proc_resources()
            res["row_id"] = rid
            res["audio_sha256"] = audio_sha
            res["identity_sha256"] = identity["identity_sha256"]
            res["judge_identity"] = {k: identity[k] for k in
                                     ("judge_source_sha256", "moe_source_sha256", "model_revision",
                                      "prompt_sha256", "decoding_config_sha256", "precision",
                                      "attention_backend", "torch_version", "placement_config",
                                      "tie_break_policy")}
            res["routing_tie_stats"] = _moe.read_tie_stats()
            if a.repeat > 1:
                res["repeat_index"] = rep
                atomic_write_json(dest.with_name(f"q3o.run-{rep:02d}.json"), res)
                runs.append(res)
            atomic_write_json(dest, res)
            results.append(res)
            rescored += 1
            failed += res["status"] == "failed"
            score = (res.get("scores") or {}).get("q3o")
            log(f"{n}/{len(rows)} {rid}" + (f" run {rep}/{a.repeat}" if a.repeat > 1 else "") +
                f": {res['status']} q3o={score} "
                f"tokens={((res.get('raw_decode') or [{}])[-1]).get('generated_tokens')} "
                f"{res['seconds']}s {('ERR ' + res['error'][:100]) if res['status'] == 'failed' else ''}")
        if a.repeat > 1 and runs:
            toks = {((r.get('raw_decode') or [{}])[-1]).get('generated_token_ids_sha256') for r in runs}
            scores = {(r.get('scores') or {}).get('q3o') for r in runs}
            log(f"[q3o-judge] {rid} repeatability over {len(runs)} runs: "
                f"token_streams={'IDENTICAL' if len(toks) == 1 else 'DIVERGED'} "
                f"scores={'IDENTICAL' if len(scores) == 1 else 'DIVERGED'} {sorted(scores)}")
    done = [r for r in results if r["status"] == "complete" and (r.get("scores") or {}).get("q3o") is not None]
    summary = {
        "schema": "yue2-rc5-q3o-run-summary/2",
        "protocol": "WSB-paper-Control-20260905-frozen-candidate-weights (frozen weights, traditional-key MIREX override, 0-5)",
        "judge_provider": "rc5_hf_transformers_rocm (ROCm-adapted; official vLLM/CUDA judge not used)",
        "identity_sha256": identity["identity_sha256"],
        "rows": len(rows), "complete": sum(1 for r in results if r["status"] == "complete"),
        "not_applicable": sum(1 for r in results if r["status"] == "not_applicable"),
        "failed": failed,
        "scored": len(done),
        "reused_receipts": reused, "rescored": rescored, "superseded_receipts": superseded,
        "q3o_mean_0_5": round(sum(r["scores"]["q3o"] for r in done) / len(done), 6) if done else None,
        "mean_seconds": round(sum(r.get("seconds", 0) for r in results) / max(1, len(results)), 2),
        "ids": [r.get("row_id") for r in results],
        "status": "COMPLETE" if done and not failed else ("COMPLETE_WITH_NOT_APPLICABLE" if not failed else "FAILED_ROWS"),
    }
    atomic_write_json(a.out / "summary.json", summary)
    log(json.dumps({k: summary[k] for k in ("rows", "complete", "not_applicable", "failed", "scored", "q3o_mean_0_5")}))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
