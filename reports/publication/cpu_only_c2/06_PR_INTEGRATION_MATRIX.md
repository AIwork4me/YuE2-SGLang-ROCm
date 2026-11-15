# C2_INTEGRATION_MATRIX（P5 Dry Run 实测）

日期：2026-11-15 · 执行方式：临时集成分支 `/tmp/c2-integration`（`tmp/c2-integration`，已从工作树移除），不触碰 main/PR head/Arm A。

## 集成链

| 步骤 | Source HEAD | 结果 |
|---|---|---|
| 1. 起点 `main`（含 PR #7） | `ba99c4d` | — |
| 2. + PR #10 head（含 PR #9 谱系 8c242ba→8756125） | `8756125` | **1 个冲突**：`.github/workflows/ci.yml`（PR#7 简化 CI vs PR#10 增强 CI）。解法=**并集**（PR#10 全部步骤 + PR#7 独有的 WSB harness 测试步骤，丢弃 PR#7 侧冗余的 compile 步骤——被 PR#10 的 scripts+supervisor 版本包含） |
| 3. + C2 | `ef3d3ab` | 干净合并（fast-forward 级） |
| 集成 HEAD | `723d8f0` | — |

## 门禁结果（全部真实执行）

| 检查 | 结果 |
|---|---|
| compileall（scripts+supervisor） | OK |
| 完整 CPU 套件 | **197 passed / 26 skipped / 0 failed** |
| public_evidence_guard | PASS |
| evidence_lyrics_detector（tier1+tier2） | **PASS 281 文件**（集成未复现任何敏感字段） |
| verify_numeric_receipt_integrity | PASS（0 漂移） |
| docs_contract | 13/13 |
| 敏感文件复现检查（per_song/.redacted 回流） | **0** |
| 协议锁 | `configs/benchmark.lock.yaml` 内容零改动（vs main 的差异为 main 缺失该文件的纯新增） |

## Security 判定

**Integration Security GO**（工作树层面）：集成分支不含歌词/转写/音素原始文本。

## PR #8 覆盖对照（P5.3，功能级非文件级）

| PR #8 功能/测试 | PR #10/C2 覆盖证据 |
|---|---|
| journal flock 串行 / torn-tail sidecar / uuid 隔离名 | PR #10 驱动实现 + C1 `test_c1_fault_injection`（真实 SIGKILL/并发） |
| worker 超时 | PR #10 实现 + C1 超时真杀测试（无孤儿、partial 保留） |
| 孤儿复用 quarantine_existing | PR #10 `resume_verified_candidate` + C1 移植测试（symlink 拒绝） |
| 8 个 PR#8 专属测试 | C1 移植 4 个（适配 PR#10 API）+ 语义覆盖 4 个；见 `cpu_only_closure/04` 映射表 |
| **PR#8 独有且未被覆盖** | **无**（逐项对照无遗漏）→ 建议 Owner 关闭为 Superseded by #10（未自动执行） |

## Owner Action Needed

1. ci.yml 冲突的并集解法需在真实合并 PR #10→main 时采用（或由 Owner 指定其它顺序）。
2. PR #8 关闭决策。
3. C2 stacked PR（base=PR#10 分支）验收后由 Owner 决定整合方式。
