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
