# RC5 — Disaster-Recovery Handoff (fresh image → resume without regenerating verified songs)

Scope: what an operator needs on a **new image** to continue the RC5 work. Every
command below was executed on the 2026-11-24 bench (evidence in
`00_RECOVERY_DRILL.json`, `03_PILOT_ACCEPTANCE.json`); commands that could not
be exercised are marked **NOT EXERCISED**.

Read first: `00_STORAGE_AND_BACKUP_PLAN.md`. There is **no off-machine backup**
(owner decision 2026-11-24: no backup host). If both the image and
`/workspace` are lost, generated audio is lost and must be regenerated
(≈ 29–35 GPU-hours); nothing in this document claims otherwise.

## 0. What exists where

| asset | location (bench) | survives image deletion? |
|---|---|---|
| code, reports, numeric evidence | GitHub `AIwork4me/YuE2-SGLang-ROCm`, branch `mission/w7900-rc5-latest-upstream-full-reproduction` | **yes** |
| campaign checkpoints (tar.zst + SHA256 manifest), every 16 candidates | `<run>/checkpoints/` and copy in `/workspace/yue2-rc5-backup/checkpoints/<run_id>/` | second volume only — **not guaranteed** |
| journals, run identity | inside every checkpoint (`journal.jsonl`, `run_config.json`, `evaluation_inputs.jsonl`) | same as above |
| models, dataset, evaluator bundle, Q3O judge | re-downloadable, SHA256-pinned | n/a |

## 1. Code at the exact commit

```bash
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git
cd YuE2-SGLang-ROCm
git checkout mission/w7900-rc5-latest-upstream-full-reproduction
# verify: the branch head must equal the SHA recorded in the PR #19 "final HEAD" comment
```

## 2. Generation environment (≈ 15 min, no GPU needed)

```bash
export YUE2_WORKSPACE=/data/yue2
sudo apt-get install -y python3.12-venv ffmpeg zstd tmux          # Ubuntu 24.04
python3.12 -m venv "$YUE2_WORKSPACE/environments/tools"           # any Python for downloads
"$YUE2_WORKSPACE/environments/tools/bin/pip" install huggingface_hub
HF_ENDPOINT=https://hf-mirror.com "$YUE2_WORKSPACE/environments/tools/bin/python" scripts/download_pins.py --workspace "$YUE2_WORKSPACE"
bash scripts/campaign_ops/rc5_build_generation_env.sh              # torch 2.12.0+rocm7.14.1 (device-gfx1100)
git clone --branch add_yue2 https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork.git "$YUE2_WORKSPACE/upstream/sglang-latest"
git -C "$YUE2_WORKSPACE/upstream/sglang-latest" checkout c67d541a40f8bf851e9fc1e925f5316638838cd6
git -C "$YUE2_WORKSPACE/upstream/sglang-latest" apply patches/rc5-0001-0003-0008-rocm-import-guards.patch
bash scripts/campaign_ops/rc5_install_sglang.sh
```

Gate — the imported code must be the audited tree:

```bash
source "$YUE2_WORKSPACE/environments/generation/bin/activate"
python scripts/rc5_runtime_manifest.py --sglang-src "$YUE2_WORKSPACE/upstream/sglang-latest" \
  --patch-file patches/rc5-0001-0003-0008-rocm-import-guards.patch \
  --out "$YUE2_WORKSPACE/logs/effective_runtime_manifest.json"
# expected: sglang_commit c67d541a…, effective_source_tree a1ca7b9f…, pip_freeze_sha256 3bea96f5…
```

A different `pip_freeze_sha256` means the venv differs from the frozen one: the
driver's identity check will then **refuse to resume** the run (by design).

## 3. Restore the campaign from checkpoints

```bash
RUN_ID=rc5_armB_latest_upstream_20261124T065451Z
RUN_DIR=/data/yue2-runs/rc5-latest-upstream-20261124T065451Z/wsb_full
BACKUP=/workspace/yue2-rc5-backup/checkpoints/$RUN_ID      # copy of this directory = the backup
# 1. verify the transferred archives (size + SHA256 against each manifest)
python scripts/rc5_backup.py verify --run-dir "$BACKUP"
# 2. restore into the run directory (never into a non-empty directory)
mkdir -p "$(dirname "$RUN_DIR")"
python scripts/rc5_backup.py restore --from "$BACKUP" --to "$RUN_DIR"
# -> RESTORE_RECEIPT.json: candidates_restored, files_verified_from_disk, journal_vs_bundles_consistent=true
```

Exercised: `verify` + `drill` on the pilot backup (4 archives, 12 candidates,
132 files hash-exact, restored FLAC identical to the live run and to the
historical frozen manifest 12/12). The campaign writes the same archive layout.

WAV files (`<run>/wavs/*.wav`) are intermediate and **not** in the checkpoints;
the official artifact is `songs/<id>/audio.flac` (restored).

## 4. Resume generation (only missing / damaged candidates are regenerated)

```bash
tmux new-session -d -s rc5gen "cd $PWD && RC5_EXPECT_GPU_BDF=0000:03:00.0 RC5_BACKUP_DIR=/workspace/yue2-rc5-backup \
  RC5_BACKUP_CLASS=same_host_second_volume bash scripts/campaign_ops/rc5_supervise.sh $RUN_DIR $RUN_ID 2>&1 | tee -a $RUN_DIR/../supervisor.log"
tail -f "$RUN_DIR/../supervisor.log"
```

On start the driver re-verifies every restored bundle with the official
checker (`verify_result`) and the run identity (`run_config.json`): verified
candidates are skipped, damaged ones are quarantined and regenerated with a
higher attempt number. Exercised by `tests/test_rc5_generate_driver.py`
(resume sends zero requests; truncated bundle → quarantine + regenerate;
identity drift → refuse rc 3) and by the real graceful interrupt on the bench.

The supervisor stops itself on a `BLOCKED` lifecycle marker or three sessions
without progress. Check before relaunching:

```bash
python scripts/gpu_lock.py status            # held=false, blocked=false
ls /data/yue2/gpu.lock.BLOCKED 2>/dev/null && cat /data/yue2/gpu.lock.BLOCKED
# resolve the recorded processes manually, then:
python scripts/gpu_lock.py unblock --yes
```

`RC5_EXPECT_GPU_BDF` must be the PCI address of the GPU the container actually
received (the run identity is bound to it); on a different card the driver
refuses to resume rather than mixing hardware.

## 5. Audit what is complete

```bash
python scripts/verify_wsb_artifacts.py --runs "$RUN_DIR"            # full: verdict must be FULL (384)
python scripts/rc5_backup.py snapshots --from "$RUN_DIR"            # archives + SHA256 to ship
```

## 6. Resume scoring

Evaluator tree + environments (CPU/network only; wheels are prefetched with
curl because uv/pip are ~30× slower behind the proxy):

```bash
bash scripts/campaign_ops/rc5_build_evaluator_tree.sh
python3 scripts/rc5_prefetch_wheels.py --lock "$YUE2_WORKSPACE/benchmark/wsb_metrics/configs/eval.installed.lock.txt" \
  --lock "$YUE2_WORKSPACE/benchmark/wsb_metrics/configs/metrics.installed.lock.txt" \
  --dest "$YUE2_WORKSPACE/tmp/wheels" --files-host https://pypi.tuna.tsinghua.edu.cn
RC5_WHEEL_DIR="$YUE2_WORKSPACE/tmp/wheels" bash scripts/campaign_ops/rc5_evaluator_install.sh
```

Scoring is idempotent: the official evaluator keeps a receipt per candidate
and only scores candidates whose receipt is missing or does not match.

```bash
bash scripts/campaign_ops/rc5_score.sh "$RUN_DIR" scores standard per,songbench
bash scripts/campaign_ops/rc5_score.sh "$RUN_DIR" additional standard mulan,allmusiccaps \
  "$RUN_DIR/scores/per_song.jsonl"
```

Killing a scoring run: stop the **evaluator parent first**, then the worker
(`pkill -f` is forbidden by policy — use the exact pids from
`gpu_lock.py status` and `pgrep -af "wsb_eval.py"`); stopping
only the worker lets the parent start the next metric outside the GPU lock.

## 7. Q3O resume — NOT EXERCISED on hardware

The Q3O judge (`scripts/rc5_q3o_judge.py`) keeps one receipt per candidate
under `--out/receipts/<id>/q3o.json` and skips candidates whose receipt is
`complete` / `not_applicable`. Its model is fetched and verified by
`scripts/rc5_download_q3o.py` (70.5 GB, SHA256 against the official asset
manifest) and linked into the evaluator tree; the traditional-key worker needs
the official key venv (`wsb_eval.py prepare --metrics q3o --install`).
**The judge itself has only passed its protocol dry-run on the bench; treat
this section as unverified until the RC5 final report says otherwise.**

## 8. Partial-evidence audit after any recovery

* `journal.jsonl`: every `result` event with `status: complete` must have a
  bundle whose `audio.flac` SHA256 equals `audio_flac_sha256` in the event
  (`rc5_backup.py restore` re-hashes restored files).
* `lifecycle/*/lifecycle-receipt.json`: `cleanup_state` must be `CLEAN` for
  finished sessions; `BLOCKED` requires operator action.
* Never delete `quarantine/`; it is the evidence of what went wrong.
