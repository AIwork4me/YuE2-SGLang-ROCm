"""rc5_generate.py driver integration test (RC5 M4.2 / M0.3 / M4.3).

Runs the REAL driver, the REAL finalize_candidate.py, the REAL official
verifier (artifact_storage.verify_result) and the official
validate_generation() of the frozen evaluator against a stub HTTP server that
mimics the SGLang artifact contract. Needs the real workspace (pinned models,
evaluator bundle) and a Python that can import sglang — everywhere else it
skips honestly.

Covers: staging -> finalize -> official verify -> atomic publish -> durable
journal -> checkpoints (+ backup re-verification), resume without
regeneration, damaged-bundle quarantine + regeneration, identity-drift
refusal, transient-failure sweeps.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("soundfile")
pytest.importorskip("sglang")

REPO = Path(__file__).resolve().parents[1]
WS = Path(os.environ.get("YUE2_WORKSPACE", "/data/yue2"))
MANIFEST = WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
MODELS = WS / "models/YuE2-3B"
EVAL = WS / "benchmark/WildSongBench/wsb_metrics"
if not (MANIFEST.is_file() and (MODELS / "model.safetensors").is_file()
        and (EVAL / "artifact_storage.py").is_file()):
    pytest.skip("workspace with pinned models + evaluator bundle not available",
                allow_module_level=True)

ROWS = {r["prompt_index"]: r for r in
        (json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip())}
WAV_SECONDS = 2.0


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Stub(BaseHTTPRequestHandler):
    server_version = "yue2-stub/1"
    fail_ids: set[str] = set()
    calls: list[str] = []

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        pl = json.loads(self.rfile.read(n))
        cid = Path(pl["artifacts_dir"]).name
        Stub.calls.append(cid)
        if cid in Stub.fail_ids:
            self._send(500, {"error": "injected"})
            return
        out, cand = Path(pl["output_path"]), Path(pl["artifacts_dir"])
        cand.mkdir(parents=True, exist_ok=True)
        wav = out / pl["output_file_name"]
        frames = int(WAV_SECONDS * 48000)
        t = np.arange(frames) / 48000.0
        audio = np.stack([0.2 * np.sin(2 * np.pi * 220 * t),
                          0.2 * np.sin(2 * np.pi * 330 * t)], axis=1)
        import soundfile as sf
        sf.write(str(wav), audio, 48000, subtype="FLOAT")
        req = {k: pl.get(k) for k in ("style", "lyrics", "cot", "seed", "abc", "cfg_scale")}
        req["id"] = pl["output_file_name"]
        (cand / "request.json").write_text(json.dumps(req, ensure_ascii=False, indent=2))
        nsem = 300
        rng = np.random.default_rng(pl["seed"])
        np.save(cand / "semantic.npy", rng.integers(0, 16000, nsem, dtype=np.int32))
        np.save(cand / "latent.npy", rng.standard_normal((nsem, 64)).astype(np.float32))
        np.save(cand / "prefix.npy", rng.integers(0, 150000, 40, dtype=np.int32))
        np.save(cand / "abc_tokens.npy", rng.integers(0, 150000, 16, dtype=np.int32))
        plan = {"request": req, "truncated": False,
                "timing": {"abc": {"seconds": 1.0, "output_tokens": 16, "truncated": False,
                                   "execution": "cuda_graph", "attention": "flash",
                                   "sampler": "reference"},
                           "semantic": {"seconds": 1.5, "output_tokens": nsem,
                                        "truncated": False, "execution": "cuda_graph",
                                        "attention": "flash", "sampler": "reference"},
                           "total_seconds": 2.5},
                "prefix": [1, 2, 3], "abc_ids": [4, 5, 6], "abc": "X:1\nT:stub\n"}
        (cand / "plan.json").write_text(json.dumps(plan, ensure_ascii=False))
        (cand / "plan_manifest.json").write_text(json.dumps({
            "plan.json": sha(cand / "plan.json"),
            "abc_tokens.npy": sha(cand / "abc_tokens.npy"),
            "prefix.npy": sha(cand / "prefix.npy")}, indent=2))
        self._send(200, {"id": cid, "audio": str(wav), "sample_rate": 48000,
                         "inference_time_s": 2.5, "peak_memory_mb": 1.0})

    def do_GET(self):
        self._send(200, {"status": "ok"})

    def log_message(self, *a):
        pass


@pytest.fixture()
def stub():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Stub.calls, Stub.fail_ids = [], set()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


_ROOTS: list[Path] = []


def big_dir(tmp_path: Path, name: str) -> Path:
    """The driver's disk guard (20 GiB floor) refuses small filesystems such
    as a tmpfs /tmp: run dirs live on the workspace filesystem."""
    import uuid
    root = Path(os.environ.get("RC5_TEST_RUN_ROOT", str(WS / "tmp/rc5_driver_test")))
    d = root / f"{name}-{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True)
    _ROOTS.append(d)
    return d


@pytest.fixture(autouse=True)
def _cleanup_roots():
    yield
    while _ROOTS:
        shutil.rmtree(_ROOTS.pop(), ignore_errors=True)


def _drive(run_dir: Path, run_id: str, url: str, *extra: str, indices=(0,)) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(REPO / "scripts/rc5_generate.py"),
           "--workspace", str(WS), "--run-dir", str(run_dir), "--run-id", run_id,
           "--server", url, "--checkpoint-every", "1", *extra]
    if indices:
        cmd += ["--indices", *map(str, indices)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def e_of(cid: str) -> tuple[int, int]:
    """wsb_000_r1_s831019 -> (0, 1); official seeds are [831001, 831019][j] + i."""
    _, i, j, seed = cid.split("_")
    return int(i), int(j[1:])


def _journal(run_dir: Path) -> list[dict]:
    return [json.loads(l) for l in (run_dir / "journal.jsonl").read_text().splitlines() if l]


def _official_accepts(cand: Path) -> None:
    sys.path.insert(0, str(EVAL / "src"))
    sys.path.insert(0, str(EVAL / "vendor"))
    code = ("import sys, json; sys.path[:0] = [%r, %r]; import wsb_eval as w; "
            "from artifact_storage import verify_result; from pathlib import Path; "
            "c = Path(sys.argv[1]); r = verify_result(c); "
            "q = json.loads((c/'request.json').read_text()); "
            "cfg = json.loads((c/'config.json').read_text()); "
            "print(json.dumps(w.validate_generation(q, cfg, r)))") % (str(EVAL / "src"), str(EVAL / "vendor"))
    r = subprocess.run([sys.executable, "-c", code, str(cand)], capture_output=True,
                       text=True, cwd=str(EVAL))
    assert r.returncode == 0, r.stderr[-800:]
    json.loads(r.stdout)


def test_generate_publish_journal_checkpoint_and_official_acceptance(tmp_path, stub):
    run = big_dir(tmp_path, "run")
    backup = tmp_path / "backup"
    r = _drive(run, "rc5test-a", stub, "--backup-dir", str(backup),
               "--backup-class", "test-destination")
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    s = json.loads((run / "generation_summary.json").read_text())
    assert s["complete"] == 2 and s["expected"] == 2 and not s["failed"]
    assert s["truncated_but_complete"] == 0
    ids = s["complete_ids"]
    assert ids == [f"wsb_000_r0_s831001", "wsb_000_r1_s831019"]
    for cid in ids:
        cand = run / "songs" / cid
        for name in ("audio.flac", "semantic.npy", "latent.npy", "prefix.npy",
                     "abc_tokens.npy", "request.json", "config.json", "plan.json",
                     "result.json", "score.abc"):
            assert (cand / name).is_file(), (cid, name)
        assert not list(cand.glob("*.wav")), "intermediate WAV leaked into the bundle"
        assert (run / "wavs" / f"{cid}.wav").is_file()
        _official_accepts(cand)
        # the seed the server RECEIVED is the official manifest seed
        i, j = e_of(cid)
        want = [831001, 831019][j] + i
        assert json.loads((cand / "request.json").read_text())["seed"] == want
        assert want == ROWS[i]["candidate_ar_seeds"][j]
        assert json.loads((cand / "result.json").read_text())["weights"]["mot"] == \
            json.loads((run / "songs" / ids[0] / "result.json").read_text())["weights"]["mot"]
    # the config carries the identity of the code that REALLY ran
    cfg = json.loads((run / "songs" / ids[0] / "config.json").read_text())
    assert len(cfg["runtime_sha256"]) == 64
    assert "sglang-latest" in cfg["rc5_runtime"]["sglang_import_path"] or \
        cfg["rc5_runtime"]["sglang_import_path"].endswith("sglang/__init__.py")
    # journal: launched before result for every candidate, receipts complete
    ev = _journal(run)
    kinds = [e["event"] for e in ev]
    assert kinds.count("launched") == 2 and kinds.count("result") == 2
    assert kinds.index("launched") < kinds.index("result")
    res = [e for e in ev if e["event"] == "result"]
    for e in res:
        assert e["status"] == "complete"
        for k in ("audio_flac_sha256", "bundle_manifest_sha256", "style_sha256",
                  "lyrics_sha256", "payload_sha256", "stage_timing", "attempt",
                  "wall_s", "audio_seconds", "rtf", "realtime_speed_multiplier"):
            assert k in e, k
        assert e["rtf"] == round(e["wall_s"] / e["audio_seconds"], 5)
        assert e["stage_timing"]["semantic"]["execution"] == "cuda_graph"
    # checkpoints exist, carry hashes, and were re-verified at the destination
    cps = [e for e in ev if e["event"] == "checkpoint"]
    assert cps and all(Path(c["archive"]).is_file() for c in cps)
    for c in cps:
        assert sha(Path(c["archive"])) == c["archive_sha256"]
    bks = [e for e in ev if e["event"] == "backup_verified"]
    assert bks and all(b["ok"] for b in bks)
    assert all(b["class"] == "test-destination" for b in bks)
    assert (backup / "checkpoints/rc5test-a").is_dir()
    # run identity is frozen and evaluation_inputs is official-shaped
    ident = json.loads((run / "run_config.json").read_text())
    assert ident["config"]["ode_steps"] == 32 and ident["config"]["semantic_max_tokens"] == 9000
    assert ident["dataset_manifest_sha256"] == sha(MANIFEST)
    assert ident["model_sha256"] == "1d55c42c1a9875c34f5d736e15078449992b044e807ce2a138e6cf289a1e59e9"
    assert ident["vae_sha256"] == "b6d283628913bb41145ba99e2314eef613905ee95f690eb70e8212d5f4965044"
    rows = [json.loads(l) for l in (run / "evaluation_inputs.jsonl").read_text().splitlines()]
    assert rows == [{"prompt_index": 0, "candidate_index": 0, "seed": 831001,
                     "path": "songs/wsb_000_r0_s831001"},
                    {"prompt_index": 0, "candidate_index": 1, "seed": 831019,
                     "path": "songs/wsb_000_r1_s831019"}]
    assert not list((run / "staging").iterdir()), "staging left debris"


def test_resume_never_regenerates_verified_candidates(tmp_path, stub):
    run = big_dir(tmp_path, "run")
    assert _drive(run, "rc5test-b", stub).returncode == 0
    before = {p.name: sha(p / "audio.flac") for p in (run / "songs").iterdir()}
    Stub.calls = []
    r = _drive(run, "rc5test-b", stub)
    assert r.returncode == 0, r.stdout + r.stderr
    assert Stub.calls == [], "a verified candidate was regenerated"
    audit = [e for e in _journal(run) if e["event"] == "resume_audit"][-1]
    assert audit["complete_verified"] == 2 and audit["missing"] == []
    assert {p.name: sha(p / "audio.flac") for p in (run / "songs").iterdir()} == before


def test_damaged_bundle_is_quarantined_and_regenerated(tmp_path, stub):
    run = big_dir(tmp_path, "run")
    assert _drive(run, "rc5test-c", stub).returncode == 0
    target = run / "songs/wsb_000_r1_s831019/audio.flac"
    good = target.read_bytes()
    target.write_bytes(good[:-4096])           # truncated after publication
    Stub.calls = []
    r = _drive(run, "rc5test-c", stub)
    assert r.returncode == 0, r.stdout + r.stderr
    assert Stub.calls == ["wsb_000_r1_s831019"], "only the damaged one was regenerated"
    audit = [e for e in _journal(run) if e["event"] == "resume_audit"][-1]
    assert [d["id"] for d in audit["damaged"]] == ["wsb_000_r1_s831019"]
    q = list((run / "quarantine").glob("*/wsb_000_r1_s831019/audio.flac"))
    assert len(q) == 1 and sha(q[0]) != sha(target)   # evidence kept, new bundle published
    ev = [e for e in _journal(run) if e["event"] == "result" and e["id"] == "wsb_000_r1_s831019"]
    assert [e["attempt"] for e in ev] == [1, 2]       # attempts are journaled


def test_identity_drift_is_refused(tmp_path, stub):
    run = big_dir(tmp_path, "run")
    assert _drive(run, "rc5test-d", stub).returncode == 0
    cfg = run / "run_config.json"
    d = json.loads(cfg.read_text())
    d["model_sha256"] = "0" * 64
    cfg.write_text(json.dumps(d))
    Stub.calls = []
    r = _drive(run, "rc5test-d", stub)
    assert r.returncode == 3 and "identity drift" in r.stdout
    assert Stub.calls == []


def test_transient_failures_are_retried_in_sweeps(tmp_path, stub):
    run = big_dir(tmp_path, "run")
    Stub.fail_ids = {"wsb_000_r1_s831019"}
    r = _drive(run, "rc5test-e", stub, "--sweeps", "1")
    assert r.returncode == 1
    s = json.loads((run / "generation_summary.json").read_text())
    assert s["complete"] == 1 and list(s["failed"]) == ["wsb_000_r1_s831019"]
    assert Stub.calls.count("wsb_000_r1_s831019") == 2   # main pass + one sweep
    # the failure never left a partial bundle behind
    assert not (run / "songs/wsb_000_r1_s831019").exists()
    assert not list((run / "staging").iterdir())
    assert (run / "quarantine").is_dir()
