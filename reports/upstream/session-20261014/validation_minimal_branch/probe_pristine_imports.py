#!/usr/bin/env python3
"""Author-baseline (pristine ced0ef7) import probe on gfx1100.

Loads the PRISTINE add_yue2 tree (no compatibility patches) with the
validation venv's interpreter, bypassing the editable finder, and records the
exact import blockers. Shared-infrastructure prerequisites are classified
separately from the YuE2 gate work.
"""
import importlib
import sys
import traceback

sys.meta_path = [f for f in sys.meta_path
                 if "editable" not in type(f).__name__.lower()]
sys.path.insert(0, "/workspace/yue2-validation/tree-pristine/python")

import sglang  # noqa: E402
print("sglang:", sglang.__file__)
assert "tree-pristine" in sglang.__file__

PROBES = [
    "sglang.srt.models.yue2",            # yue2 package itself
    "sglang.srt.layers.quantization.quark.schemes.quark_w4a4_mxfp4",
    "sglang.srt.layers.quantization.quark_int4fp8_moe",
    "sglang.srt.mem_cache.hisparse_memory_pool",
    "sglang.srt.mem_cache.memory_pool_host",
]

failures = {}
for mod in PROBES:
    try:
        importlib.import_module(mod)
        print(f"OK       {mod}")
    except Exception:
        tb = traceback.format_exc().strip().splitlines()
        failures[mod] = tb
        print(f"FAIL     {mod}")
        for line in tb[-4:]:
            print(f"         {line}")

print("\n=== summary ===")
for mod, tb in failures.items():
    last = [l for l in tb if "Error" in l or "error" in l]
    print(f"{mod}: {last[-1].strip() if last else tb[-1].strip()}")
