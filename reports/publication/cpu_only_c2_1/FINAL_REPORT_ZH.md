# C2.1 Final Fail-Closed Closure — 中文最终报告

执行：2026-11-15T12:18–12:40 UTC · 分支 `fix/c2-1-final-fail-closed-closure`
（base=PR #11 `4d9f4a2`）· 本地 243 passed / 0 failed / 26 skipped · 变异 5/5 KILLED

## 修复了什么（Before→Fix→测试，详见 01–06 号文档）

1. **P0-A 整包原子性**：staging→审计→renameat2(NOREPLACE) 单点提交；失败
   final 永不存在；既有包字节不变；双进程竞争恰一胜者（真实进程测试）。
2. **P0-B No-Clobber**：os.link 原子提交替代 exists+replace 竞争窗口；
   file/symlink/dangling 全拒；6轮真实双进程竞争零失真；inode 身份检查。
3. **P0-C Provenance 全链**：journal↔launched↔result↔session↔快照闭环+
   四级证据分层（BYTE/CROSS_CHECKED/PRESENT/LEGACY）+孤儿检测+新格式损坏
   不降级；20 项负向对照全落。
4. **P1-A 快照不可变**：类型先行（内容正确的 symlink 也拒）+tmp+link 崩溃
   安全写；双进程同/异 SHA 真实并发测试。
5. **P1-B 测试完整性**：真 mid-copy TOCTOU（确定性屏障，无随机 sleep）；
   AST 级无效断言清零；权限断言精确化；变异控制 5/5 KILLED（含暴露并
   补齐 M3 收据绑定缺口）。

## Benchmark 语义变化：**无**
协议锁/PER 工具/数值收据/seeds/模型全零改动（07 文档 diff 为证）。
C2.1 changes publication mechanics, not measured science.

## Arm A 未受影响（证据边界）
零 GPU 命令、零 `/data/yue2-runs/armA_wsb_full` 访问（除只读 journal 计数
59→61/384）、零进程干预、独立 clone 作业；运行树 8c242ba 未触碰。

## 仍 BLOCKED
G3（close() 显存）· G10（AR Hang/HIP 根因）· G15（版权历史+权利）·
G20 及全部 campaign 依赖项（Gate D 物理）。

## 三判定

**A. C2.1 CPU-only Engineering：GO**
五项全部 Reproduce→Root Cause→Fix→正/负对照→回归→变异→本地全绿；无未决
CPU 缺陷。

**B. C2 CPU Engineering Freeze：GO**
C2+C2.1 合并审阅面完整（证据分层/原子发布/溯源闭环）；建议冻结点=本 PR 被
Owner 接受之时。继续 CPU 扩展只会违背"测试数量≠缺陷关闭"原则。

**C. Full YuE2 ROCm Benchmark Publication：NO-GO**
Arm A 61/384 进行中；四指标未产；PER 17.77 vs 8.44 因果未闭合；G3/G10/G15
BLOCKED。A/B 的 GO 不替代 C。

## 下一步（资源转向）
Arm A 384/384 → 官方四指标 → Arm B 复现 → PER Cross-Evaluator（受限包）→
AR Hang → HIP fault → G20 真实溯源 → G15 处置。

---

## 2026-11-16 Final Freeze Independent Audit（后补审阅；优先于前述旧状态）

### 发现并关闭的新问题

1. **Legacy → New-format 同 Candidate 合法重试误判**：旧失败事件位于 Journal 原生前缀，后续同 Candidate 的新格式 Attempt 有独立 Journal + Launched/Result/Session 链时，应如实计为 `LEGACY_PROVENANCE_INCOMPLETE`，而非仅因当前存在其 Provenance 目录便误判损坏。若缺少后续新格式 Journal，仍 Fail Closed。明确拒绝新格式开始后的无标记记录，且若删掉旧新格式事件的关联，Result 会作为 Orphan 报错。
2. **Result-only Orphan 漏检**：新增单独遍历 `*.result.json`；Complete 和 Failed 两种无 Launched、无 Journal 的结果均拒绝。Launched-only / 未产生 Result 的真实崩溃状态继续如实报告，不能冒充已验证完成。
3. **音频私密暂存目录**：所有新建 Staging 与其 audio 子目录以 `0700` 创建；清理失败打印明确的受限 Staging 人工处置警告，不再 `ignore_errors=True` 静默丢失证据；音频复制与最终审计收据写入时的 OS 错误通过相同 Fail-Closed 路径终止。

### 新增合成 CPU 正反测试

`tests/test_c2_1_final_freeze.py` 中的 8 项测试分别验证：合法同 Candidate legacy failed→new complete、升级后无标记事件拒绝、新事件删源字段的 Orphan 检测、Complete/Failed result-only orphan、合法 launched-only 崩溃、私密完整包权限、清理失败告警与权限、最终 audit 记录 I/O 失败时原子退出。

以上为代码和测试交付；**最终 GitHub exact-HEAD CI 数字与链接以 PR #12 运行结果为准，不得沿用旧 `241/28` 的 HEAD。**

### 验收边界

- 这是 **GitHub + CPU synthetic-data only**；没有物理 GPU 访问，未读取真实歌词或音频，没有 Arm A 部署。
- 新旧混合历史只能证明记录按 append-order 兼容、且新 Attempt 链完整；**没有外部签名或可信 Cutover Ledger 时，不能从任意可被篡改的 JSON 单独证明历史真实性**。Legacy 始终 `INCOMPLETE/UNKNOWN`，不是新式字节级 Provenance VERIFIED。
- 私有 Staging 清理失败可能留下 `0700` 的隔离残留（绝不成为正式包）；仍需 Owner 在受限工作区手动清理，禁止把残留复制到公开仓库。
- G3/G10/G15 仍 BLOCKED，G20 NOT_TESTED，所有依赖 GPU/完整评分的发表门禁不因 CPU CI 成功解锁。
- PR #12 继续 Draft；通过最终 CI 后方可建议 **CPU-only Freeze GO for Owner Review**，不等于合并或 Publication GO。
