# 03 — Provenance 完整身份验证 RCA（P0-C）

## Before（4d9f4a2 验证器的缺口）
只对 journal↔launched/result 做了部分字段比对：无 driver session 核验、
无坐标/seed 闭环、无孤儿收据检测、损坏的新格式记录可借"无 attempt_id"
滑入 LEGACY 逃逸验证；证据等级混称 VERIFIED。

## Fix（scripts/verify_provenance.py 重写）
完整链：`Journal →attempt_id→ Launched →attempt/candidate/seed/coords→
Result →session_id→ DriverSession →worker_sha→ WorkerSnapshot(字节级)；
driver_sha=收据间交叉`。逐记录字段对应关系全覆盖（见 verify_record）。

**四级证据分层（summary.evidence_levels，永不混称）**：
- `BYTE_HASH_VERIFIED`：worker 快照（盘上重哈希）；
- `RECEIPT_CROSS_CHECKED`：driver sha（三收据一致；驱动源码在 git，无盘上
  快照——明示不可证明字节未变）；
- `RECEIPT_PRESENT`：session runtime 环境；
- `LEGACY/UNKNOWN`：旧格式记录（仅当 legacy worker 哈希==run_config 记录
  才给 RUN_LEVEL_VERIFIED 归因）。

**新格式损坏≠Legacy**：带任何溯源字段、或盘上存在该候选收据的记录缺
attempt_id → `PROVENANCE_VIOLATION`（两测试证明不降级）。

**孤儿收据**：complete 结果收据无 journal 记录（crash-after-commit）→
VIOLATION（journal 少计=完整性破坏）；仅 launched → 摘要报告不计违规
（诚实崩溃现场）。

**只读保证**：AST 级测试断言验证器无 write/unlink/chmod/link/rename/mkdir
调用；输出无歌词/转写。

## 负向对照（20 项清单全落测试）
tests/test_c2_provenance.py::TestC21FullChainNegatives 17 项 + 既有 3 项
（tampered/missing snapshot、duplicate attempt）= mission §5.3 的 1–20 全集，
其中 18 项 → VIOLATION，2 项（crash-before-journal 的 launched-only、旧格式）
→ 摘要级 LEGACY/orphan 报告（如实分类，非降级逃逸）。

## 2026-11-16 追加：混合代际 Journal 与 Result-only 盲区

原实现依据 `provenance/<candidate_id>/` **是否存在**来判断旧 Journal 无 attempt_id 的行是否损坏。这会把合理的 append-only `old failed → new complete` 混合历史误判。

新规则：Journal 第一条带任意 Provenance 字段的记录建立 **格式切换边界**；更早的无标记事件按历史前缀核查。若该 Candidate 现在有新版 Attempt 目录，只在**它后面**有同 Candidate 的完整新格式 Journal 事件时允许历史分类；后续新格式链必须独立验证。切换边界之后出现无标记 Journal 一律拒绝。只有新版 Result 收据且无 Launched/Journal 的孤儿必须拒绝。独立测试证明假删字段的旧新格式事件因遗留 Complete Result 孤儿而不能逃逸。

限制：Journal 记录目前没有外部签名或不可篡改的旧代 Cutover Ledger，故分类属于 **prefix-consistent legacy UNKNOWN**，绝非证明过去确实由特定代码运行。若存在复杂并发跨代写入，必须人工冻结/审计，不准自动恢复为 VERIFIED。
