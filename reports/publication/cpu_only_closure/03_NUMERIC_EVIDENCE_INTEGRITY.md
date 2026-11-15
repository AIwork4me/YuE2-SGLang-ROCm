# 03 — 数值证据完整性（C1 P1.3 实测）

工具：`scripts/verify_numeric_receipt_integrity.py`（本 C1 新增，CI 接入）。
对照：`8c242ba`（脱敏前，PR #9 head）→ `HEAD`（本分支，含 PR #10 数值收据）。

## 结果：PASS（零漂移）

| 文件 | 行数(原→新) | identity 字段 | 数值叶 |
|---|---|---|---|
| evidence/evaluator_audit/per_runA_2candidates.jsonl | 2→2 | 不变 | 全等 |
| evidence/evaluator_audit/per_runB_10candidates.jsonl | 10→10 | 不变 | 全等 |
| evidence/evaluator_audit/per_runC_10candidates_repeat.jsonl | 10→10 | 不变 | 全等 |
| evidence/publication/armA_pilot/per_song.jsonl | 2→2 | 不变 | 全等 |
| evidence/gfx1100/scoring_snapshot.json | — | — | 1851 共享叶子 0 漂移 |

被比较的身份字段：id / prompt_index / candidate_index / seed / sample_id /
clip_id / result_sha256 / audio_sha256 / generator_identity /
generation_condition / status 等 19 项，逐候选全等。
数值叶：metrics 下全部 int/float/bool（TEXT_KEYS 除外）逐路径全等。

## Fail-closed 语义

- `--orig-ref` 不存在 → exit 2（拒绝空洞 PASS；测试覆盖）。
- 行数漂移 / id 丢失 / 数值增删改 → 逐条列出并 FAIL。
- CI（fetch-depth: 0）在每次 push/PR 运行；无 `|| true` 掩盖。

## 被删除原始文件的科学可核性（mission 3.3 要求的清单）

| 原始路径 | 删除于 | 保留的科学证据 | 独立复核是否需要受限原件 |
|---|---|---|---|
| evidence/per_song.jsonl（384 行全文本） | PR#10 4dc29f0 | 数值收据文件（本文件验证）；sha8 歌词指纹可对受限原件核对 | **是**（PER 复核/跨评测器研究需 transcript，受限存储授权后可取） |
| evidence/gfx1100/scoring_snapshot.json（全文本版） | 同上 | 同文件数值化版本（1851 叶子全等） | 部分（transcript 级复核需原件） |
| *.redacted.* 早期副本 | 同上 | 数值收据更彻底（副本仅哈希化 key 名仍敏感） | 否 |
| evidence/publication/armB_campaign/*（数值型） | 未删 | 完整保留 | 否 |

**结论**：脱敏未损失任何数值科学证据；文本级复核（PER 转写比对）依赖受限
原件，已在 02 号文档的受限备份方案中安排——可验证性未因脱敏丢失。
