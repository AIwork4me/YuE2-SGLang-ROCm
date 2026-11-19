# 05 — PER 分析工具审阅与边界测试（C1 P3）

对象：PR #10 重写后的 `scripts/per_tail_analysis.py`、
`scripts/build_per_reference_package.py`（含 6f7eddc rights-gate）。

## 1. 选择正确性（mission 5.1）

- `(per or 1)` 真值 bug：**已彻底移除**——现为显式 `a < b` 比较；PER=0 可被
  正确选中（`test_zero_per_is_selected_without_truthiness_bug`）。
- PER 相等：无官方 selection 时 raise（不得本地猜测 tie-break）。
- **发表级选择唯一来源**：`scores/summary.json::selected_candidates`
  （192 项），并交叉验证 seed 与 audio_sha256 与候选身份一致；
  `selection_provenance=OFFICIAL_SELECTED_CANDIDATES_VERIFIED`。
  诊断模式输出显式标注 `DIAGNOSTIC_MIN_PER_ONLY_NOT_OFFICIAL`。
- 边界实测（C1 gap 探针，直接调用 choose_rows）：
  - seed 不一致 → `Official seed mismatches candidate identity` ✓
  - 官方 selection 缺失/不足 192 → 长度校验拒绝 ✓
  - 候选缺失/重复/坐标非法/phonemes<=0 → 各自 raise ✓

## 2. 总体分离（mission 5.2）

三种总体独立统计：`selected_192` / `unselected_192` / `all_384`，各带
candidates/edits/phonemes/micro_per；bootstrap CI 仅对 selected 报告。
工具内建 warning：分解的是**当前 selected-192 PER**，不是与官方 8.44% 的
因果差——禁止把 Unselected/All-384 与官方 selected-192 相减。

## 3. 互斥分组与守恒（mission 5.3）

- capped × empty(含 UNKNOWN=None) **6 格互斥划分**，运行时断言：
  候选数和=192、edits 和=selected edits、phonemes 和=selected phonemes
  （`test_disjoint_partition_sums_to_selected_aggregate`）。
- **PER=1.0 ≠ 空转写**：`empty` 字段仅在转写文本可取得时判定，文本已
  脱敏的公开收据上一律 `None=UNKNOWN`（`test_per_one_does_not_imply_empty_
  transcript`）。公开分析将 10 个 PER=1 候选标注为"1.0 值计数"而非"空"。

## 4. 参考 ASR 对照包（mission 5.4）

`build_per_reference_package.py`（PR10 已 rights-gate，C1 复核）：

- 仅使用官方 selected（需真 official summary 才可运行——
  `test_handoff_requires_true_official_summary`）。
- 参考值仅保留数值（per/edits/phonemes/truncated），
  `test_numeric_reference_record_cannot_publish_lyrics` 断言无歌词字段。
- 无权利标志不拷贝任何音频（`test_no_audio_is_copied_without_rights_flag`）。
- 缺文件 fail-closed；文件名来自官方 id 模式（无路径注入面）。
- **本 C1 未打包任何音频**（Arm A 未完成，且需 Owner 权利确认）；
  **未运行官方参考 ASR → 跨评测器一致性未验证，不做任何一致宣言**。

## 5. 结论

PER 工具链（选择/总体/分组/守恒/UNKNOWM 语义/权利门）经 CPU 测试与边界
探针全部通过；剩余依赖（Arm A/B 完成 → 官方 per_song+summary → 官方
selection 驱动的发表级分析 → 受限对照包）列于 FINAL_REPORT 下一步表。
