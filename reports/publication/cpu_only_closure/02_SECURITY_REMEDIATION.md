# 02 — 安全修复与全分支泄漏矩阵（C1 P1）

## 1. 新工具：真值歌词检测器（本 C1 新增）

`scripts/evidence_lyrics_detector.py` —— 双层扫描：

- **Tier 1（恒开）**：结构化文件 key 扫描（fail-closed：解析失败即违规；
  数值/布尔/已知安全枚举/digest 字符串白名单——`asr_repeats` 数值收据、
  `target: gfx1100`、`reference_phonemes: 384` 均正确放行）。
- **Tier 2（有冻结 manifest 时）**：从数据集**真实歌词**提取归一化 16 字符
  指纹窗（仅 `lyrics` 字段、CJK≥4 行；`style` 标签是事实性元数据，指纹它
  会在英文文档产生 "male vocals mandarin" 类误报——已实测并排除），匹配
  **所有跟踪文件**的归一化文本——key 名无关、扩展名无关、嵌套无关。
- 输出纪律：只报 文件+sha8，绝不打印匹配文本。

### 设计依据的实测（Before → After）

- 初始 tier2（含 style 指纹）：44 处发现 → 其中 20 处为 style 误报（英文
  文档正常提及标签），收紧后归零误报。
- 白名单缺失时 `asr_repeats` 数值收据被误报 26 处 → 加入
  "容器内全部叶节点为数值/布尔/安全枚举/digest" 规则后归零。

## 2. 全分支泄漏矩阵（2026-11-15 实测，tier1+tier2 双开）

| Ref（PR） | 结果 |
|---|---|
| `main` | **FAIL 1637**（`evidence/per_song.jsonl` 等原始文本仍在） |
| `feat/yue2-rocm-publication-readiness`（#8/#9 的 base） | **FAIL 1637** |
| `mission/w7900-fresh-image-final-closure`（PR #9 head=8c242ba） | **FAIL 1685**（原始 + 早期 redacted 副本残留） |
| `fix/w7900-armA-journal-quarantine-20261115`（PR #8 head） | **FAIL 1637** |
| `fix/w7900-cpu-only-risk-closure-20261115`（PR #10 head=78c5cb8） | **PASS（257 文件，0 发现）** |
| `security/redact-historical-wsb-lyrics-20261115`（PR #7 head） | **PASS（179 文件，0 发现）** |

（发现数上限 200 文件截断；FAIL 分支的真实总数≥1637。）

**结论**：当前公开树层面，仅 PR #7（对 main）与 PR #10（对 mission 分支）
的 head 干净。合并这两者后，工作树层面修复完成。

## 3. PR #7 / PR #10 脱敏实现审阅（mission 3.2 逐项）

| 检查项 | 结果 |
|---|---|
| 短文本（<50 字符）敏感 key | detector 测试覆盖：仍被抓（无长度豁免）✓ |
| 嵌套数组 ASR 转写 | `asr_repeats[].text/raw_chunks` 原文件已删/数值化；detector 对嵌套 `text` 抓取有测试 ✓ |
| Phoneme token 数组 | `reference_tokens` 原文件已删；detector 测试：字符串 token 数组不放行 ✓ |
| 原始 target 对象 | 已从公开树删除（git 显示于 4dc29f0）✓ |
| 模型/音频身份 hash 保留 | 数值完整性验证（03 号文档）：identity 字段零变化 ✓ |
| 数值指标不变 | 1851 共享数值叶子 0 漂移 ✓ |
| 候选数量不变 | 24/24 行、id/seed 零变化 ✓ |
| Scoring summary 完整 | scoring_snapshot.json 1851 叶子对齐 ✓ |
| 旧原始文件是否仍在当前树 | 否（detector PASS 证实）✓ |
| 后续运行是否会把敏感文件带回 | 两个机制：(a) CI guard+detector（本 C1 已接入 ci.yml，含 PR 事件）；(b) `evidence/per_song.jsonl` 列入 guard 的 NOT_PUBLIC 禁止清单——重新提交即 CI 失败 ✓ |

## 4. Git 历史与版权（不可执行项的处置方案）

当前树修复≠历史删除。以下为**已准备但不执行**（需 Owner 批准）：

- **历史对象清单**：泄漏文件的引入提交（`1f23c8e`、`ebb6995`、`9e489c6`
  等）与可达分支（本矩阵第 2 节全部 FAIL ref）；GitHub Fork/缓存存在性
  需 Owner 在 GitHub 侧核实（API 匿名 fork 枚举不可靠）。
- **受限原始证据备份方案**：在受控主机对 8c242ba 树的原始 per-song 数据
  打包（sha256 清单），供独立复核——原始数据本就在 git 历史内，备份仅是
  将其从"公开可达"迁移到"受限可达"。
- **GitHub Support 协调方案**：若 Owner 选择 B（历史改写+force push），
  需同时请求 GitHub 清理缓存对象与 fork 网络；改写将使本矩阵全部 ref SHA
  失效——PR #7/#8/#9/#10/CI run 链接全部需要重建（风险见 06 号文档）。
- **数据集作者授权沟通材料**：请求 m-a-p 对"研究性引用+脱敏收据"方式的
  追认（Option C），附本矩阵与脱敏工具的可复现说明。
- **推荐**：Option A（HEAD 换脱敏副本+README 声明+受限备份）风险最低；
  B 仅在作者拒绝 A/C 时考虑。

## 5. PR #7 合并条件审阅（mission 3.6）

- Diff 最小化：evidence 文件删除/替换 + guard 新增，无科学指标改动（数值
  完整性对 main 侧同样成立——PR7 的替换文件与 8c242ba 原件数值一致，
  已由 verify_numeric_receipt_integrity 在 PR10 侧验证同源语义）。
- CI：PR #7 head CI 通过（cpu SUCCESS）。
- 保护规则：main 无分支保护；**但本次未获明确合并授权 → 保持 Draft，
  标记 Review-Ready**；GO/NO-GO 台账见 06 号文档。
