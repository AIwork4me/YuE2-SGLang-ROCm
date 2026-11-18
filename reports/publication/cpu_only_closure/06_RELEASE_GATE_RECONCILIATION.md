# 06 — Release Gate 对账与文档一致性（C1 P4）

## 1. Gate 逐项对账（fresh_image/FINAL_RELEASE_GATE_LEDGER.json，C1 后状态）

| Gate | C1 前状态 | C1 动作 | C1 后状态 | 依据 |
|---|---|---|---|---|
| G0 环境验证 | PASS | 复核 | PASS | 00_ENVIRONMENT + GPU smoke |
| G1 三环境依赖收据 | BLOCKED（两个 evaluator freeze 空） | **根因修复**：uv venv 无 pip → 用评估器自带 `uv pip list` 重生成（metrics 232 包 / eval 76 包，torch 替换可见） | **PASS** | dependency_inventory/ 5/5 非空；根因记录于 02_INSTALLATION 更新 |
| G2 官方 pin | PASS | 复核 | PASS | phase3_download_manifest |
| G3 API 验收 | BLOCKED | 保持 | **BLOCKED**（正确） | `close()` 显存未解，residual_risk 原文保留"requires later physical analysis or owner waiver"——不得删失败项换 14/14 |
| G4-G9,G11-G14,G16-G17,G19 | NOT_TESTED | 保持 | NOT_TESTED | 依赖 campaign/GPU/Owner，无 CPU 可推进项 |
| G10 缺陷修复 | BLOCKED | 保持 | **BLOCKED**（正确分离） | CPU 工具链已完成（136+162 测试）**与** GPU 根因（AR Hang、HIP fault）未完成——台账原文即如此拆分，未宣称"全部缺陷已修复" |
| G15 安全许可 | BLOCKED | 保持 | **BLOCKED**（部分关闭如实） | 当前树修复≠历史/权益关闭；Owner 决策待定 |
| G18 上游归属 | PASS | 复核+08 文档 | PASS | UPSTREAM_PR_PLAN |

**历史台账**（reports/publication/RELEASE_GATE_LEDGER.json）：F6 规范化状态
（PASS/FAIL/BLOCKED/NOT_TESTED + historical_status 保留原文）经测试守护，
C1 无变更需要。

## 2. 文档一致性核查（mission 6.5 逐项）

| 项 | 结果 | C1 动作 |
|---|---|---|
| README 标题重复 | 存在 H1/H2 半重复 + **字面 `\n\n` 渲染 bug** | 已修（escape 修复） |
| README 旧状态当新状态 | 硬件表混排历史/新镜像 | 已标注 **HISTORICAL** vs **THIS MISSION'S RIG** |
| 上次 384/384 ≠ 本次 | README/RESULTS 已区分（7 处 historical 标注） | 保持 |
| PER 17.77 vs 8.44 | RESULTS.md 明示 "not aligned; cross-backend RCA OPEN" | 保持 |
| close() 披露 | G3 residual_risk + PYTORCH_API_ACCEPTANCE 双处 | 保持 |
| Q3O | KNOWN_LIMITATIONS 两处 NOT TESTED | 保持 |
| 命令可复制/链接有效 | docs_contract 测试在 CI 守护 | 保持（CI 绿） |
| 无 CPU 未测项标 PASS | gate 状态即证据 | 保持 |

## 3. PR #7 GO/NO-GO 台账（Owner 合并决策用）

| 条件 | 状态 |
|---|---|
| 当前树安全（双 tier 扫描 PASS） | ✅（PR7 head 实测） |
| 数值完整性 | ✅（同源语义于 PR10 侧验证；PR7 替换文件数值等价） |
| CI | ✅ cpu SUCCESS |
| Diff 最小化/无指标改动 | ✅ |
| 历史对象处置 | ⚠️ 不在本 PR 范围（02 文档方案待批） |
| **合并授权** | ❌ 未获得 → **保持 Draft / Review-Ready** |

PR #10：CI 绿 + 安全绿 + 审阅完成（01/04/05 文档）→ 可由 Owner 决定推进
review；**不合并到 main**（其 base 是 mission 分支）。

## 2026-11-15 最终同步状态

- PR #7：已 MERGED，合并提交 `ba99c4d`，不再处于 Owner 待合并状态。
- PR #8：Draft，驱动语义与 PR #10 重叠，保留证据；未经 Owner 确认不自动关闭。
- PR #9：Draft / 基线不变；Arm A 使用的旧驱动不得热替换。
- PR #10：仍是 Draft；本轮只做 CPU-only 防护与科学一致性审阅，不自动合并到 PR #9 或 main。
- G1 PASS，G3/G10/G15 BLOCKED；G15 的最新风险包含真实数据集 Tier 2 不在公开 CI、历史 Git 对象/旧分支/许可处置。G5/G6/G7/G8/G9/G11 等 GPU/第三方专属 Gate 不得被转换成 PASS。
- C1 报告中任何旧 136/162 或 113/138 测试数，只能根据其精确 commit/run 描述；使用 PR #10 末次 HEAD 的 GitHub Actions 作为最新结论。
