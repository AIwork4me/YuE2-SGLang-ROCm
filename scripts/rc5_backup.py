#!/usr/bin/env python3
"""rc5_backup.py — checkpoint verification, restore and disaster-recovery drill
(RC5 M0.3 / M9.4).

A campaign (scripts/rc5_generate.py) writes, every N complete candidates, an
incremental checkpoint and, at the milestone counts, a FULL checkpoint plus a
restore manifest. Each archive carries a manifest with the SHA256 of every
file it contains.

    verify   --run-dir D            every checkpoint archive + manifest + member hashes
    restore  --from D --to D2       rebuild a run into an INDEPENDENT directory
    drill    --from D --to D2       restore + verify + write a machine-readable receipt

`--from` may be the campaign directory itself OR a backup copy of its
`checkpoints/` directory (the drill restores from the backup, never from the
live run). The tool never writes into the source and never trusts a file
whose size or SHA256 does not match the manifest.

Off-machine synchronisation is deliberately NOT built in as a silent default:
`snapshots` only lists what has to be shipped. Shipping requires an operator
authorised destination (see 00_STORAGE_AND_BACKUP_PLAN.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_archive(path: Path):
    """Streaming reader for .tar and .tar.zst."""
    if path.name.endswith(".zst"):
        proc = subprocess.Popen(["zstd", "-dc", str(path)], stdout=subprocess.PIPE)
        return tarfile.open(fileobj=proc.stdout, mode="r|"), proc
    f = open(path, "rb")
    return tarfile.open(fileobj=f, mode="r|"), f


def _close_archive(tf, fh) -> None:
    """Close the tar stream and its zstd subprocess / file handle."""
    try:
        tf.close()
    except (tarfile.TarError, OSError):
        pass
    if isinstance(fh, subprocess.Popen):
        try:
            fh.stdout.close()
        except OSError:
            pass
        fh.wait()
    else:
        fh.close()


def load_journal(run_dir: Path) -> list[dict]:
    j = run_dir / "journal.jsonl"
    out, torn = [], 0
    if j.is_file():
        for line in j.read_text().splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                torn += 1
    return out


def checkpoints_of(src: Path) -> list[dict]:
    """``src`` is a run directory (checkpoints/ inside) or a backup copy of a
    run's checkpoint directory (archives directly inside)."""
    base = src / "checkpoints" if (src / "checkpoints").is_dir() else src
    cps = sorted(base.glob("*.manifest.json"))
    out = []
    for m in cps:
        man = json.loads(m.read_text())
        archive = next((p for p in (m.with_name(m.name.replace(".manifest.json", ".tar.zst")),
                                    m.with_name(m.name.replace(".manifest.json", ".tar")))
                        if p.is_file()), None)
        out.append({"manifest": m, "manifest_obj": man, "archive": archive,
                    "kind": man["kind"], "complete_count": man["complete_count"],
                    "created_at_utc": man["created_at_utc"]})
    return out


def verify_archive(cp: dict) -> dict:
    res = {"archive": str(cp["archive"]), "kind": cp["kind"],
           "complete_count": cp["complete_count"], "errors": []}
    man = cp["manifest_obj"]
    if cp["archive"] is None:
        res["errors"].append("archive missing")
        return res
    res["archive_bytes"] = cp["archive"].stat().st_size
    res["archive_sha256"] = sha256_file(cp["archive"])
    tf, fh = _open_archive(cp["archive"])
    seen: dict[str, dict] = {}
    try:
        for member in tf:
            if not member.isfile():
                continue
            h = hashlib.sha256()
            f = tf.extractfile(member)
            for chunk in iter(lambda: f.read(8 << 20), b""):
                h.update(chunk)
            seen[member.name] = {"sha256": h.hexdigest(), "bytes": member.size}
    except (tarfile.TarError, OSError) as e:
        res["errors"].append(f"unreadable archive: {type(e).__name__}: {e}")
    finally:
        _close_archive(tf, fh)
    res["members"] = len(seen)
    # every candidate file listed in the manifest must be in the archive, hash-exact
    missing, wrong = [], []
    for cid, files in man["candidates"].items():
        for rel, want in files.items():
            name = f"{cid}/{rel}"
            got = seen.get(name)
            if got is None:
                missing.append(name)
            elif got["sha256"] != want["sha256"] or got["bytes"] != want["bytes"]:
                wrong.append(name)
    if missing:
        res["errors"].append(f"{len(missing)} manifest file(s) missing from the archive")
    if wrong:
        res["errors"].append(f"{len(wrong)} file(s) with wrong size/sha256")
    for key, name in (("run_config_sha256", "run_config.json"),
                      ("evaluation_inputs_sha256", "evaluation_inputs.jsonl"),
                      ("journal_sha256", "journal.jsonl")):
        if man.get(key) and seen.get(name, {}).get("sha256") != man[key]:
            res["errors"].append(f"{name} hash differs from the manifest")
    res["candidates_in_archive"] = len(man["candidates"])
    res["ok"] = not res["errors"]
    return res


def verify(src: Path) -> dict:
    cps = checkpoints_of(src)
    results = [verify_archive(cp) for cp in cps]
    return {"source": str(src), "checkpoints": len(cps),
            "ok": bool(cps) and all(r["ok"] for r in results), "results": results}


def restore(src: Path, to: Path) -> dict:
    """Rebuild the run into ``to`` from the checkpoints under ``src``.

    Base = every archive in chronological order; candidate directories are
    the union (a file is only accepted when its hash matches the manifest of
    the checkpoint that carries it)."""
    if to.exists() and any(to.iterdir()):
        raise SystemExit(f"refusing to restore into a non-empty directory: {to}")
    to.mkdir(parents=True)
    (to / "songs").mkdir()
    cps = checkpoints_of(src)
    if not cps:
        raise SystemExit(f"no checkpoints under {src}/checkpoints")
    accepted: dict[str, dict] = {}
    conflicts, rejected = [], []
    newest_journal, newest_cfg, newest_inputs = None, None, None
    journal_seq = -1
    per_cp = []
    for cp in cps:
        man = cp["manifest_obj"]
        tf, fh = _open_archive(cp["archive"])
        count = 0
        try:
            for member in tf:
                if not member.isfile():
                    continue
                f = tf.extractfile(member)
                data = f.read()
                digest = hashlib.sha256(data).hexdigest()
                name = member.name
                if name.startswith("wsb_") and "/" in name:
                    cid, rel = name.split("/", 1)
                    want = man["candidates"].get(cid, {}).get(rel)
                    if want is None:
                        rejected.append(name)
                        continue
                    if digest != want["sha256"] or len(data) != want["bytes"]:
                        rejected.append(name)
                        continue
                    target = to / "songs" / cid / rel
                    if cid in accepted and rel in accepted[cid] and accepted[cid][rel] != digest:
                        conflicts.append(name)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        with open(target, "wb") as fh:
                            fh.write(data)
                            fh.flush()
                            os.fsync(fh.fileno())
                    accepted.setdefault(cid, {})[rel] = digest
                    count += 1
                    continue
                # run-level files: the newest checkpoint wins
                if name == "journal.jsonl" and cp["complete_count"] >= journal_seq:
                    (to / "journal.jsonl").write_bytes(data)
                    newest_journal, journal_seq = digest, cp["complete_count"]
                elif name == "run_config.json":
                    (to / "run_config.json").write_bytes(data)
                    newest_cfg = digest
                elif name == "evaluation_inputs.jsonl":
                    (to / "evaluation_inputs.jsonl").write_bytes(data)
                    newest_inputs = digest
        finally:
            _close_archive(tf, fh)
        per_cp.append({"archive": os.path.basename(cp["archive"]), "kind": cp["kind"],
                       "files_accepted": count})
    # re-verify every restored file from disk
    disk_ok, disk_bad = 0, []
    for cid, files in accepted.items():
        for rel, digest in files.items():
            p = to / "songs" / cid / rel
            if p.is_file() and sha256_file(p) == digest:
                disk_ok += 1
            else:
                disk_bad.append(f"{cid}/{rel}")
    journal = load_journal(to)
    complete_in_journal = {e["id"] for e in journal if e["event"] == "result"
                           and e.get("status") == "complete"}
    have = set(accepted)
    cfg = json.loads((to / "run_config.json").read_text()) if (to / "run_config.json").is_file() else {}
    inputs = [json.loads(l) for l in (to / "evaluation_inputs.jsonl").read_text().splitlines() if l.strip()] \
        if (to / "evaluation_inputs.jsonl").is_file() else []
    receipt = {
        "schema": "yue2-rc5-restore-receipt/1",
        "restored_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(src), "destination": str(to),
        "checkpoints_applied": per_cp,
        "candidates_restored": len(have),
        "candidate_ids": sorted(have),
        "files_verified_from_disk": disk_ok, "files_bad_on_disk": disk_bad,
        "rejected_mismatching_members": rejected, "conflicting_members": conflicts,
        "journal_events": len(journal),
        "journal_complete_ids": sorted(complete_in_journal),
        "journal_vs_bundles_consistent": complete_in_journal == have,
        "journal_sha256": newest_journal,
        "run_config": {k: cfg.get(k) for k in ("run_id", "arm", "dataset_revision",
                                               "dataset_manifest_sha256", "model_revision",
                                               "model_sha256", "vae_revision", "vae_sha256",
                                               "config")} if cfg else None,
        "run_config_sha256": newest_cfg,
        "evaluation_inputs_rows": len(inputs),
        "evaluation_inputs_sha256": newest_inputs,
        "expected_candidates_from_inputs": len(inputs),
        "missing_vs_inputs": sorted({f"wsb_{e['prompt_index']:03d}_r{e['candidate_index']}_s{e['seed']}"
                                     for e in inputs} - have),
        "ok": bool(have) and not disk_bad and not conflicts
              and complete_in_journal == have and bool(cfg) and bool(inputs),
    }
    (to / "RESTORE_RECEIPT.json").write_text(json.dumps(receipt, indent=1) + "\n")
    return receipt


def snapshots(src: Path) -> dict:
    cps = checkpoints_of(src)
    return {"source": str(src), "checkpoints": len(cps),
            "total_bytes": sum(c["archive"].stat().st_size for c in cps if c["archive"]),
            "archives": [{"name": os.path.basename(c["archive"]), "kind": c["kind"],
                          "complete_count": c["complete_count"], "bytes": c["archive"].stat().st_size,
                          "sha256": sha256_file(c["archive"])}
                         for c in cps if c["archive"]]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--run-dir", type=Path, required=True)
    v.add_argument("--out", type=Path, default=None)
    for name in ("restore", "drill"):
        s = sub.add_parser(name)
        s.add_argument("--from", type=Path, required=True,
                       help="run dir OR a backup copy containing checkpoints/")
        s.add_argument("--to", type=Path, required=True)
        s.add_argument("--out", type=Path, default=None)
    sn = sub.add_parser("snapshots")
    sn.add_argument("--from", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "verify":
        r = verify(a.run_dir)
        text = json.dumps(r, indent=1) + "\n"
        if a.out:
            a.out.write_text(text)
        print(json.dumps({k: r[k] for k in ("source", "checkpoints", "ok")}))
        for x in r["results"]:
            print(f"  {x['kind']:12s} n={x['complete_count']:3d} members={x.get('members')} "
                  f"{'OK' if x['ok'] else 'ERROR ' + '; '.join(x['errors'])}")
        return 0 if r["ok"] else 1
    if a.cmd in ("restore", "drill"):
        r = restore(getattr(a, "from"), a.to)
        text = json.dumps(r, indent=1) + "\n"
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(text)
        print(json.dumps({k: r[k] for k in ("candidates_restored", "files_verified_from_disk",
                                            "journal_events", "journal_vs_bundles_consistent",
                                            "expected_candidates_from_inputs", "ok")}, indent=1))
        if r["files_bad_on_disk"] or r["rejected_mismatching_members"] or r["conflicting_members"]:
            print("bad:", r["files_bad_on_disk"][:5], "rejected:", len(r["rejected_mismatching_members"]),
                  "conflicts:", r["conflicting_members"][:5])
        return 0 if r["ok"] else 1
    print(json.dumps(snapshots(getattr(a, "from")), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
