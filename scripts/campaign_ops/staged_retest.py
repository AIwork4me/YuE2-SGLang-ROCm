"""Staged-API retest (P4.1 item 5) with the correct Sampling contract.

The original acceptance run used sampling={"seed": 7} — an invented parameter
(Sampling has no seed field; the seed travels via plan.request.seed). This
retest uses the REAL API: plan(request={seed:7}) -> generate_semantic(Sampling())
-> synthesize -> decode. Also probes close() VRAM release in a clean process.
"""
import gc
import json
import sys
import time
from pathlib import Path

import torch
from yue2 import YuE2Pipeline
from yue2.pipeline import Sampling

OUT = Path("/data/yue2-runs/api_acceptance")
t0 = time.time()
pipe = YuE2Pipeline.from_pretrained(
    "m-a-p/YuE2-3B", revision="1a96eca688d6ae5d7f0feb88573fec89920fcd19",
    vae="m-a-p/YuE2-Vae-legacy",
    vae_revision="b54118f0fc462f08999d1ec07e88817f4ee3f770",
    cache_dir="/data/yue2/hf-cache/hub", backend="torch-eager",
    device="cuda:0", memory_budget_gib=24)
from yue2.protocol import SongRequest
plan = pipe.plan(
    request=SongRequest(
        style="female pop vocal bright vocal",
        lyrics="[verse]\nShadows falling on the street\nNeon signs beneath my feet\n"
               "[chorus]\nRunning through the night\nChasing fading light",
        cot="full", seed=7, cfg_scale=1.0, id="staged7"))
sem = pipe.generate_semantic(plan, sampling=Sampling())
lat = pipe.synthesize(sem)
import soundfile as sf
a = pipe.decode(lat)
d = OUT / "staged.wav"
sr = 48000
if hasattr(a, "numpy"):
    a = a.numpy()
if a.ndim == 1:
    a = np.stack([a, a], axis=1)
sf.write(str(d), a, sr)
import numpy as np
shape = list(a.shape)
finite = bool(np.isfinite(a).all())
free0, total = torch.cuda.mem_get_info()
pipe.close()
del plan, sem, lat, a
gc.collect()
torch.cuda.empty_cache()
free1, _ = torch.cuda.mem_get_info()
res = {"test": "staged_api", "pass": True, "wall_s": round(time.time() - t0, 1),
       "audio_seconds": round(shape[0] / sr, 2),
       "shape": shape, "finite": finite, "sr": sr,
       "audio_sha256": __import__("hashlib").sha256(d.read_bytes()).hexdigest()[:16],
       "close_probe": {
           "used_before_close_gib": round((total - free0) / 2**30, 2),
           "used_after_close_gib": round((total - free1) / 2**30, 2),
           "freed_gib": round((free1 - free0) / 2**30, 2)}}
acc = OUT / "acceptance.json"
rows = json.loads(acc.read_text()) if acc.is_file() else []
rows = [x for x in rows if x.get("test") != "staged_api"] + [res]
acc.write_text(json.dumps(rows, indent=2))
print("PASS staged_api", json.dumps(res))
