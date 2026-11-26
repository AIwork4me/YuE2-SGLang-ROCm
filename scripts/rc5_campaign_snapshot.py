#!/usr/bin/env python3
"""Numeric-only public snapshot of an RC5 campaign journal.

Publishes an allow-list of fields (ids, timings, hashes, counters) from
journal.jsonl plus the lifecycle lines of supervisor.log. Benchmark text
(prompts, lyrics, transcripts) is never read from the candidate bundles and
never written here.

Usage:
  python3 scripts/rc5_campaign_snapshot.py --run-root <dir> --out report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROW_FIELDS = ["id", "prompt_index", "candidate_index", "seed", "attempt", "status",
              "truncated", "audio_seconds", "codec_frames", "wall_s", "ar_seconds",
              "nar_seconds", "vae_seconds", "rtf", "realtime_speed_multiplier",
              "audio_flac_sha256", "wav_sha256", "wav_bytes", "bundle_files",
              "bundle_bytes", "candidate_vram_delta_bytes"]
FLAC_INFO_FIELDS = ["samplerate", "channels", "frames", "subtype"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-root", required=True, help="campaign run root (contains wsb_full/ and supervisor.log)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = Path(args.run_root)
    journal = root / "wsb_full" / "journal.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]

    def first(event):
        return next((r for r in rows if r["event"] == event), None)

    results = [r for r in rows if r["event"] == "result"]
    launched = first("launch")
    first_candidate_launch = next((r for r in rows if r["event"] == "launched"), launched)
    summary = next((r for r in rows if r["event"] == "summary"), None)
    # the LAST summary is the run's final state (the first may be an
    # intermediate pause, e.g. the RC5 SIGTERM snapshot at 20/384)
    for r in rows:
        if r["event"] == "summary":
            summary = r
    checkpoint = next((r for r in rows if r["event"] == "checkpoint"), None)
    for r in rows:
        if r["event"] == "checkpoint":
            checkpoint = r          # newest checkpoint
    backup = next((r for r in rows if r["event"] == "backup_verified"), None)
    candidates = []
    for r in sorted(results, key=lambda r: (r["prompt_index"], r["candidate_index"])):
        row = {k: r.get(k) for k in ROW_FIELDS}
        row["flac_info"] = {k: r.get("flac_info", {}).get(k) for k in FLAC_INFO_FIELDS}
        candidates.append(row)

    walls = [r["wall_s"] for r in results]
    supervisor = (root / "supervisor.log").read_text(errors="replace")
    exits = re.findall(r"\[rc5-supervise\] session \d+ exited rc=(\d+) (\S+)", supervisor)
    backup_ids = json.loads(Path(checkpoint["manifest"]).read_text())["candidates"] if checkpoint else {}
    complete_ids = [r["id"] for r in candidates if r["status"] == "complete"]

    report = {
        "schema": "yue2-rc5-campaign-snapshot/1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"run_root": str(root), "journal": str(journal),
                   "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest(),
                   "supervisor_log": str(root / "supervisor.log"),
                   "supervisor_exits_rc_ts": [{"rc": int(rc), "at": at} for rc, at in exits]},
        "run_id": launched["run_id"],
        "server": {"pid": launched["server"]["pid"], "port": launched["server"]["port"],
                   "argv_sha256": launched["server"]["argv_sha256"]},
        "gpu": first_candidate_launch.get("gpu"),
        "driver_runtime_sha256": first_candidate_launch.get("runtime_sha256"),
        "expected": launched["expected"],
        "complete": summary["complete"] if summary else None,
        "failed": summary["failed"] if summary else {},
        "stopped_by_signal": summary["stopped_by_signal"] if summary else None,
        "server_unusable": summary["server_unusable"] if summary else None,
        "wall_seconds": {"mean": round(statistics.mean(walls), 1), "median": round(statistics.median(walls), 1),
                         "min": round(min(walls), 1), "max": round(max(walls), 1),
                         "projected_remaining_hours_for_the_rest":
                             round((launched["expected"] - len(results)) * statistics.mean(walls) / 3600, 1)},
        "checkpoint": None if not checkpoint else {
            "kind": checkpoint["kind"], "complete_count": checkpoint["complete_count"],
            "created_utc": checkpoint["ts"], "bytes": checkpoint["bytes"],
            "archive_name": Path(checkpoint["archive"]).name,
            "archive_sha256": checkpoint["archive_sha256"],
            "manifest_sha256": checkpoint["manifest_sha256"]},
        "backup": None if not backup else {
            "class": backup["class"], "destination": backup["destination"], "verified_ok": backup["ok"],
            "candidate_ids_in_checkpoint": sorted(backup_ids)},
        "complete_not_in_checkpoint_backup": [i for i in complete_ids if i not in backup_ids],
        "candidates": candidates,
        "notes": "Numeric allow-list only. Audio, prompts and evaluator artefacts stay on the bench "
                 "machine; this file is safe to publish (checked by the evidence guards).",
    }
    Path(args.out).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(f"complete={report['complete']}/{report['expected']} "
          f"not_in_backup={len(report['complete_not_in_checkpoint_backup'])} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
