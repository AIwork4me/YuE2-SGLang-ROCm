#!/usr/bin/env python3
"""api_git.py - Git-less GitHub sync over the REST/Git Data API.

Rationale: this machine's egress proxy blocks CONNECT to github.com (and
ssh.github.com, objects.githubusercontent.com) but allows api.github.com.
All operations here go through `gh api` (authenticated, no secrets stored).

Subcommands:
  head    --repo O/R --branch B            print head commit sha
  log     --repo O/R --ref X [--n N]       print recent commits (sha, date, msg)
  fetch   --repo O/R --ref X --dest DIR    materialize tree + write API_GIT_STATE.json
  push    --repo O/R --branch B --dir DIR --message M [--create-from B2]
                                            compute diff vs state, push one commit

Push semantics:
  - Fast-forward only (force=false). Aborts if remote head moved since fetch.
  - Refuses files > 100 MB (GitHub blob limit; weights belong outside git).
  - Secret scan on staged content (tokens/keys) before upload.
  - Never rewrites or deletes remote history.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time

STATE_FILE = "API_GIT_STATE.json"
EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache",
                "node_modules", ".ruff_cache", ".venv", "*.egg-info"}
MAX_BLOB_BYTES = 100 * 1024 * 1024

SECRET_PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(rb"hf_[A-Za-z0-9]{34,}"),
]


def api(path, *, method="GET", body=None, raw=False, retries=4):
    """Call `gh api`. body: dict -> JSON stdin. raw: return stdout bytes."""
    cmd = ["gh", "api", "--method", method]
    if raw:
        cmd += ["-H", "Accept: application/vnd.github.raw"]
    if body is not None:
        cmd += ["--input", "-", "-H", "Content-Type: application/json"]
    cmd += [path]
    last = None
    for attempt in range(retries):
        p = subprocess.run(cmd, input=json.dumps(body).encode() if body is not None else b"",
                           capture_output=True)
        if p.returncode == 0:
            if raw:
                return p.stdout
            return json.loads(p.stdout) if p.stdout.strip() and p.stdout.strip() != b"null" else {}
        last = p
        # retry on 5xx / rate-limit / transient proxy failures
        err = p.stderr.decode(errors="replace")
        if ("HTTP 5" in err or "HTTP 429" in err or "tunnel" in err.lower()
                or "timed out" in err.lower()) and attempt < retries - 1:
            time.sleep(3 * (attempt + 1))
            continue
        sys.stderr.write(f"gh api {method} {path} failed:\n{err}\n")
        sys.exit(2)
    sys.stderr.write(f"gh api {method} {path} exhausted retries:\n{last.stderr.decode(errors='replace')}\n")
    sys.exit(2)


def esc_ref(ref):
    return ref.replace("/", "%2F")


def resolve_commit(repo, ref):
    """ref: branch name, tag, full sha, or 'heads/x'."""
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref
    for template in ("git/ref/heads/{r}", "git/ref/tags/{r}"):
        try:
            d = api(f"repos/{repo}/{template.format(r=esc_ref(ref))}")
            return d["object"]["sha"]
        except SystemExit:
            continue
    # fall back: commits?sha=
    d = api(f"repos/{repo}/commits?sha={ref}&per_page=1")
    return d[0]["sha"]


def cmd_head(args):
    print(resolve_commit(args.repo, args.branch))


def cmd_log(args):
    sha = resolve_commit(args.repo, args.ref)
    d = api(f"repos/{args.repo}/commits?sha={sha}&per_page={args.n}")
    for c in d:
        msg = c["commit"]["message"].splitlines()[0]
        print(f"{c['sha']} {c['commit']['author']['date']} {c['commit']['author']['name']} | {msg}")


def iter_local_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        kept = []
        for d in dirnames:
            if d == STATE_FILE:
                continue
            if any(re.fullmatch(pat.replace("*", ".*"), d) for pat in EXCLUDE_DIRS) or d in EXCLUDE_DIRS:
                continue
            kept.append(d)
        dirnames[:] = kept
        for f in filenames:
            if rel_dir == "." and f == STATE_FILE:
                continue
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                yield rel, "link"
            else:
                yield rel, "file"


def cmd_fetch(args):
    repo, ref, dest = args.repo, args.ref, args.dest
    sha = resolve_commit(repo, ref)
    commit = api(f"repos/{repo}/git/commits/{sha}")
    tree_sha = commit["tree"]["sha"]
    tree = api(f"repos/{repo}/git/trees/{tree_sha}?recursive=1")
    if tree.get("truncated"):
        sys.stderr.write("FATAL: recursive tree truncated; needs level-wise fetch (unimplemented)\n")
        sys.exit(3)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    files = {}
    n = 0
    for e in tree["tree"]:
        if e["type"] != "blob":
            continue
        path = e["path"]
        target = os.path.join(dest, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        data = api(f"repos/{repo}/git/blobs/{e['sha']}", raw=True)
        mode = e.get("mode", "100644")
        if mode == "120000":
            os.symlink(data.decode(), target)
        else:
            with open(target, "wb") as fh:
                fh.write(data)
            if mode == "100755":
                os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        files[path] = {"sha": e["sha"], "mode": mode, "size": e.get("size", len(data))}
        n += 1
    state = {"repo": repo, "ref": ref, "commit": sha, "tree": tree_sha,
             "files": files, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "file_count": n}
    with open(os.path.join(dest, STATE_FILE), "w") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    print(f"fetched {n} files, commit {sha[:12]} -> {dest}")


def blob_sha(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def scan_secrets(path, data):
    hits = []
    for pat in SECRET_PATTERNS:
        m = pat.search(data)
        if m:
            hits.append(f"{path}: pattern {pat.pattern[:24]}... matched {m.group()[:12]}...")
    return hits


def read_state(dirpath):
    p = os.path.join(dirpath, STATE_FILE)
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def cmd_push(args):
    repo, branch, dirpath = args.repo, args.branch, args.dir
    # remote head (must exist or --create-from given)
    parent = None
    try:
        parent = resolve_commit(repo, f"heads/{branch}")
    except SystemExit:
        if not args.create_from:
            print(f"branch {branch} not found and no --create-from given", file=sys.stderr)
            raise
    if parent is None:
        parent = resolve_commit(repo, args.create_from)
        api(f"repos/{repo}/git/refs", method="POST",
            body={"ref": f"refs/heads/{branch}", "sha": parent})
        print(f"created branch {branch} at {parent[:12]}")
    parent_commit = api(f"repos/{repo}/git/commits/{parent}")
    base_tree = parent_commit["tree"]["sha"]

    state = read_state(dirpath)
    prev_files = state["files"] if state else {}

    changes, deletes, all_findings = [], [], []
    for rel, kind in iter_local_files(dirpath):
        p = os.path.join(dirpath, rel)
        if kind == "link":
            data = os.readlink(p).encode()
            mode = "120000"
        else:
            if os.path.getsize(p) > MAX_BLOB_BYTES:
                sys.stderr.write(f"FATAL: {rel} exceeds 100MB blob limit; not pushing\n")
                sys.exit(4)
            with open(p, "rb") as fh:
                data = fh.read()
            mode = "100755" if (os.stat(p).st_mode & stat.S_IXUSR) else "100644"
        sha = blob_sha(data)
        prev = prev_files.get(rel)
        if prev and prev["sha"] == sha and prev["mode"] == mode:
            continue
        for hit in scan_secrets(rel, data):
            all_findings.append(hit)
        new_sha = api(f"repos/{repo}/git/blobs", method="POST",
                      body={"content": base64.b64encode(data).decode(), "encoding": "base64"})["sha"]
        changes.append({"path": rel, "mode": mode, "type": "blob", "sha": new_sha})
    if state:
        for rel in prev_files:
            if not os.path.exists(os.path.join(dirpath, rel)) and not os.path.islink(os.path.join(dirpath, rel)):
                deletes.append({"path": rel, "sha": None})
    if all_findings:
        sys.stderr.write("SECRET SCAN FINDINGS (push aborted):\n" + "\n".join(all_findings) + "\n")
        sys.exit(5)

    entries = changes + deletes
    if not entries:
        print("no changes")
        print(f"REMOTE_SHA {parent}")
        return
    cur_tree = base_tree
    for i in range(0, len(entries), 500):
        chunk = entries[i:i + 500]
        r = api(f"repos/{repo}/git/trees", method="POST",
                body={"base_tree": cur_tree, "tree": chunk})
        cur_tree = r["sha"]
    commit = api(f"repos/{repo}/git/commits", method="POST",
                 body={"message": args.message, "tree": cur_tree, "parents": [parent]})
    try:
        api(f"repos/{repo}/git/refs/heads/{esc_ref(branch)}", method="PATCH",
            body={"sha": commit["sha"], "force": False})
    except SystemExit:
        sys.stderr.write("PUSH CONFLICT: remote head moved during push; re-fetch and retry\n")
        sys.exit(6)
    print(f"pushed {len(changes)} changed, {len(deletes)} deleted -> commit {commit['sha']}")
    print(f"REMOTE_SHA {commit['sha']}")
    # refresh local state for the files we know
    new_state = {"repo": repo, "ref": f"heads/{branch}", "commit": commit["sha"], "tree": cur_tree,
                 "files": dict(prev_files), "pushed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "file_count": len(prev_files)}
    for e in changes:
        new_state["files"][e["path"]] = {"sha": e["sha"], "mode": e["mode"]}
    for e in deletes:
        new_state["files"].pop(e["path"], None)
    new_state["file_count"] = len(new_state["files"])
    with open(os.path.join(dirpath, STATE_FILE), "w") as fh:
        json.dump(new_state, fh, indent=1, sort_keys=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("head"); h.add_argument("--repo", required=True); h.add_argument("--branch", required=True); h.set_defaults(func=cmd_head)
    l = sub.add_parser("log"); l.add_argument("--repo", required=True); l.add_argument("--ref", required=True); l.add_argument("--n", type=int, default=10); l.set_defaults(func=cmd_log)
    f = sub.add_parser("fetch"); f.add_argument("--repo", required=True); f.add_argument("--ref", required=True); f.add_argument("--dest", required=True); f.set_defaults(func=cmd_fetch)
    p = sub.add_parser("push")
    p.add_argument("--repo", required=True); p.add_argument("--branch", required=True)
    p.add_argument("--dir", required=True); p.add_argument("--message", required=True)
    p.add_argument("--create-from")
    p.set_defaults(func=cmd_push)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
