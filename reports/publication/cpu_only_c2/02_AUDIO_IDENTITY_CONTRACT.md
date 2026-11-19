# 02 — 音频身份契约（C2 P2）

## 缺陷（Before）

旧打包实现：按 candidate ID 找 `audio.flac` → 复制 → 对**输出**算 SHA。
ID 正确但 flac 被换过时，导出仍"合法"——**文件名≠证据**。

## Schema 事实（先读冻结源码，不猜测）

`wsb_eval.py:290-313`（标准模式评分链）：

```
candidate/audio.flac --ffmpeg 192k libmp3lame--> report/audio/<id>/audio.mp3
row.audio_sha256 == sha256(audio.mp3)                      ← 评分输入身份
report/audio/<id>/encoding.json:
    mp3_sha256        == sha256(audio.mp3)                 ← 编码绑定
    source_flac_sha256== sha256(candidate/audio.flac)      ← flac 绑定
```

## 身份链（After）

```
Official Selected Candidate
  → ID / prompt_index / candidate_index / seed          （官方 selection）
  → per_song receipt.audio_sha256 (= mp3)               （评分身份）
  → encoding.mp3_sha256 == receipt.audio_sha256          （链1）
  → sha256(mp3 现存字节) == mp3_sha256                   （链2：未变造）
  → encoding.source_flac_sha256 == sha256(source flac)   （链3：flac 即评分源）
  → sha256(copied flac) == source_flac_sha256            （链4：拷贝忠实）
  → bytes 相等 + O_EXCL + 只读导出                        （链5：无覆盖/无转码）
```

每样本记 `audio_identity_verdict`（仅 `AUDIO_IDENTITY_VERIFIED` 可入包）。

## Fail-Closed 清单（全部实现+测试）

ID 不合法/目录穿越/symlink · 候选或 seed 不一致（经官方 selection 分层验证）
· 源缺失 · encoding 收据缺失（=**无法证明该 flac 是被评分音频**→拒绝）
· mp3 与收据不符 · flac 与收据不符 · 拷贝中源变化（TOCTOU）· 大小不符 ·
目标已存在（禁覆盖）· 无 `--rights-confirmed` · 逐样本失败→**整包拒绝**
（不留半成品）。

## 权利

`--rights-confirmed` 是操作者声明（脚本不授予权利）；导出文件 0444 只读；
真实音频未在 C2 打包（Arm A 未完成+权利未确认）；测试全部合成字节。

## 测试（tests/test_c2_audio_identity.py，11 个）

全链 PASS（含只读导出断言）· 换 flac→拒 · 缺 encoding→拒 · symlink→拒 ·
穿越 ID→拒 · mp3 变造→拒 · 目标存在→拒 · 缺权利标志→拒 · 源中途变化→拒 ·
selection 缺 audio_sha256（COORDINATES-only）→拒（打包要求完全验证层）。
