# 00 STORAGE PLAN — Fresh Image

Chosen after inspecting actual volumes (no pre-existing `/data`; `/tmp` is a 4G
tmpfs; `/workspace` is a 98G loop; `/` is a 3.5T overlay with 1.6T free).

## Layout (on `/`, the only large persistent volume)

```
/data/yue2/                 # workspace root (YUE2_WORKSPACE)
    models/                 # pinned wheels + model/VAE snapshots (SHA256-verified by download_pins.py) ~16 GB
    hf-cache/               # HF_HOME (offline-mode warm cache)
    environments/           # yue2-torch (Arm A), sglang (Arm B) venvs
    upstream/               # sglang tarball + patched git tree
    benchmark/              # WildSongBench + wsb_metrics evaluator tree (+ .venvs, evaluation_models)
    logs/                   # all campaign/scoring logs (never /tmp)
    tmp/                    # TMPDIR for everything heavy (mode 1777)

/data/yue2-runs/            # campaign outputs (audio bundles, journals, scores)
    armA_wsb_full/
    armB_wsb_full/
    per_rca/                # Phase P6 controlled experiments
    performance/            # Phase P9 measurements (kept separate from quality runs)
```

## Constraints honored

- **Cgroup RAM ceiling 55 GiB**: single heavyweight GPU process at a time;
  page-cache accumulation from audio I/O is watched (`memory.current`) per
  handoff gotcha 13.
- **`/tmp` never used** for models, campaigns, pip TMPDIR or HF cache.
- **Est. capacity**: models ~16 GB + 3 envs ~30 GB + evaluator weights ~20 GB +
  two campaigns × (384 × ~30–60 MB audio ≈ 15–25 GB) + logs — well within 1.6T.
- **Durability policy**: audio artifacts are regenerable from pinned seeds; the
  audited evidence, hashes and manifests are committed to git as they are
  produced (handoff §8).
