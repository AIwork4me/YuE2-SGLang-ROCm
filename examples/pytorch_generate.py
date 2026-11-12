#!/usr/bin/env python3
"""examples/pytorch_generate.py — first YuE2 song on AMD ROCm (native PyTorch).

Verification status: the underlying pipeline calls and parameters mirror the
official `code/generate.py` recipe verified on W7900 (2026-11-12); this
convenience wrapper is exercised in the Phase 3 acceptance window.

Usage:
    source $YUE2_WORKSPACE/environments/yue2-torch/bin/activate
    export HF_HOME=$YUE2_WORKSPACE/hf-cache
    python examples/pytorch_generate.py --output outputs/first_song
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--model", default="m-a-p/YuE2-3B")
    ap.add_argument("--revision",
                    default="1a96eca688d6ae5d7f0feb88573fec89920fcd19")
    ap.add_argument("--vae", default="m-a-p/YuE2-Vae-legacy")
    ap.add_argument("--vae-revision",
                    default="b54118f0fc462f08999d1ec07e88817f4ee3f770")
    ap.add_argument("--seed", type=int, default=831001)
    ap.add_argument("--cot", default="full", choices=("full", "melody", "off"))
    args = ap.parse_args()

    from yue2 import YuE2Pipeline  # torch-eager path on ROCm (see docs)

    request = {
        "id": "first_song",
        # ORIGINAL demo lyrics (do not use WildSongBench content for demos).
        "style": "[Tags]\nfemale vocal, warm indie pop, acoustic guitar, 96 bpm\n",
        "lyrics": ("[Lyrics]\n[Verse]\nMorning light on the harbor line\n"
                   "Coffee steam and a quiet sign\n[Chorus]\nStay a while, "
                   "stay a while\nThe city wakes in a crooked smile\n"),
        "cot": args.cot,
        "cfg_scale": 1.0,
        "seed": args.seed,
    }
    with YuE2Pipeline.from_pretrained(
            args.model, revision=args.revision, vae=args.vae,
            vae_revision=args.vae_revision, backend="torch-eager",
            device="cuda:0", memory_budget_gib=24) as pipe:
        song = pipe(**request)
        song.save_artifacts(args.output)
        print(json.dumps({
            "truncated": song.truncated,
            "audio_seconds": song.audio_seconds if hasattr(song, "audio_seconds") else None,
            "output": str(args.output),
        }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
