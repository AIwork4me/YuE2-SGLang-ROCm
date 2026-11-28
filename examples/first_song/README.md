# First-song example (original content)

These lyrics and style tags were written specifically for this repository's
first-song acceptance path. They are ORIGINAL works created for the
YuE2-on-ROCm reproduction reference and are free to use, modify and
redistribute for any purpose (no restrictions — unlike the WildSongBench
dataset lyrics, which are NOT redistributable and never appear in this
repository).

- `style.txt` — English style/tags block
- `lyrics_en.txt` — original English lyrics (verse/chorus/outro)
- `lyrics_zh.txt` — original Chinese lyrics

One-command use (from the repo root):

```bash
python3 scripts/reference_cli.py generate \
  --lyrics examples/first_song/lyrics_en.txt \
  --style examples/first_song/style.txt \
  --seed 831001 --out-dir "$YUE2_WORKSPACE/runs/my-first-song"

python3 scripts/reference_cli.py verify --run-dir "$YUE2_WORKSPACE/runs/my-first-song"
```

Acceptance criteria for a FIRST_SONG pass are defined in
`reports/developer_reference/05_DEVELOPER_JOURNEY.md` (SMOKE_AUDIO_PASS vs
FULL_SONG_PASS) — a full song must be a complete musical piece (not a
truncated smoke clip), 48 kHz stereo, non-silent, GPU-executed, with the
official model identity bound in the candidate bundle.
