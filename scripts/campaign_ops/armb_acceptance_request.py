#!/usr/bin/env python3
"""armb_acceptance_request.py — REAL music-generation acceptance for Arm B.

A /health 200 and a /v1/models advertisement prove a server process exists;
they prove NOTHING about music generation. This helper issues one bounded,
full-pipeline generation request (AR + NAR + VAE decode) through the same
/v1/audio/generations endpoint the campaign driver uses, then validates the
returned audio is real, decodable, non-silent music of non-trivial length.

Exit 0 only when every check passes; the receipt (with SHA256 of the audio)
is written next to the audio for the evidence chain. Smoke parameters are
NOT the frozen benchmark protocol (short original lyrics, reduced semantic
budget) and are labeled as such in the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Original lyrics written for this acceptance (no third-party rights).
SMOKE_LYRICS = (
    "[verse]\n"
    "Morning light on the harbor wall\n"
    "A copper bell begins to call\n"
    "[chorus]\n"
    "Run the river, chase the tide\n"
    "Leave the old road far behind\n"
)
SMOKE_STYLE = ("[Genre] folk, pop\n[Instrument] acoustic guitar, light drums\n"
               "[Mood/Theme] warm, hopeful\n[Vocal] female, clear")

SMOKE_PARAMS = {  # bounded smoke generation — deliberately NOT protocol values
    "cot": "full", "abc": None,
    "ode_steps": 32, "semantic_max_tokens": 1200, "abc_max_tokens": 1024,
    "vae_core_frames": 512, "vae_halo_frames": 16,
}
MIN_DURATION_S = 5.0
MIN_RMS = 1e-4


def post_generation(server: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        f"{server}/v1/audio/generations",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def validate_audio(wav: Path) -> dict:
    import numpy as np
    import soundfile as sf
    data, sr = sf.read(wav, always_2d=True)
    duration = len(data) / sr
    rms = float(np.sqrt(np.mean(np.square(data.astype(np.float64)))))
    return {"sample_rate": sr, "channels": data.shape[1],
            "frames": len(data), "duration_s": round(duration, 3),
            "rms": rms,
            "checks": {
                "duration_ok": duration >= MIN_DURATION_S,
                "non_silent_ok": rms >= MIN_RMS,
                "frames_ok": len(data) > 0,
            }}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--out-dir", required=True, help="acceptance evidence dir")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="bounded generation wait (server-side full-song path)")
    ap.add_argument("--seed", type=int, default=20261119)
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "acceptance_smoke.wav"
    payload = {
        "style": SMOKE_STYLE, "lyrics": SMOKE_LYRICS, "seed": args.seed,
        "output_path": str(out), "output_file_name": wav.name,
        "artifacts_dir": str(out / "artifacts"), "id": "armB_acceptance_smoke",
        **SMOKE_PARAMS,
    }
    t0 = time.monotonic()
    try:
        resp = post_generation(args.server, payload, args.timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"ACCEPTANCE_FAIL: generation request failed: "
              f"{type(exc).__name__}: {exc}")
        return 1
    wall_s = round(time.monotonic() - t0, 1)

    if not (resp.get("audio") or wav.is_file()):
        print(f"ACCEPTANCE_FAIL: no audio produced (response: {str(resp)[:300]})")
        return 1
    if not wav.is_file():
        print(f"ACCEPTANCE_FAIL: server reported audio but file missing: {wav}")
        return 1

    try:
        audio_info = validate_audio(wav)
    except Exception as exc:
        print(f"ACCEPTANCE_FAIL: audio not decodable: {type(exc).__name__}: {exc}")
        return 1
    if not all(audio_info["checks"].values()):
        print(f"ACCEPTANCE_FAIL: audio checks failed: {audio_info}")
        return 1

    receipt = {
        "what": "armB real music-generation acceptance (smoke, non-protocol)",
        "server": args.server,
        "seed": args.seed,
        "wall_s": wall_s,
        "audio_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
        "audio_bytes": wav.stat().st_size,
        "audio": audio_info,
        "response_excerpt": {k: v for k, v in resp.items()
                             if k != "audio" and isinstance(v, (str, int, float, bool))},
        "params": SMOKE_PARAMS,
    }
    (out / "acceptance_receipt.json").write_text(json.dumps(receipt, indent=1))
    print(f"ACCEPTANCE_PASS: {audio_info['duration_s']}s "
          f"@{audio_info['sample_rate']}Hz rms={audio_info['rms']:.4f} "
          f"wall={wall_s}s sha256={receipt['audio_sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
