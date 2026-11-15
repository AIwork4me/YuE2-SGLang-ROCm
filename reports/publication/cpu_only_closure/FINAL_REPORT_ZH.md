# C1 CPU-Only Engineering Closure — 中文最终报告

执行窗口：2026-11-15T05:23–06:00 UTC · 分支：`audit/c1-cpu-only-integration`（= PR #10 head `fix/w7900-cpu-only-risk-closure-20261115` @ `bba98d3`+本提交）
CI：https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/43682957300 （success）

---

## 1. 完成了什么（全部落地为代码+测试+提交）

1. **真值歌词检测器**（`scripts/evidence_lyrics_detector.py`）：双 tier
   （key 扫描 + 数据集真实歌词指纹窗），fail-closed，输出永不含原文；
   13 个合成测试（无任何真实歌词进 CI）。
2. **全分支泄漏矩阵**：main / feat / PR#8 / PR#9 head 均 **FAIL（≥1637 发现）**；
   仅 PR #7 与 PR #10 head **PASS** —— 安全合并路径由此确定。
3. **数值证据完整性工具**（`verify_numeric_receipt_integrity.py`）：
   脱敏前后 24 候选行、19 项身份字段、1851 数值叶子 **零漂移**；bad-ref
   fail-closed（exit 2）；接入 CI（fetch-depth:0，无任何 `|| true`）。
4. **真实故障注入套件**（`test_c1_fault_injection.py`，12 测试）：真实
   SIGKILL 中断写、双进程并发竞争（80/80 无损）、worker 超时（真杀+无孤儿
   +partial 保留）、torn/内部损坏/越界/symlink 全阻断；并移植 PR #8 的
   互补测试价值（4 项，适配 PR #10 API）。
5. **修复 CI 盲区里的陈年缺陷**：`test_wsb_full_mode` fixture 缺
   identity/config——在 8c242ba 即 5 failed（**非** PR#8/#10 回归，git
   证据+worktree 复测）；修复后 12/12，且新增 forged-identity 负向对照。
6. **G1 证据补全**：两个空 evaluator freeze 根因（uv venv 无 pip）→ 用
   评估器自带 uv 生成真收据（metrics 232 / eval 76 包）→ G1 诚实转 PASS。
7. **README 修复**：字面 `\n` 渲染 bug + 硬件表 **HISTORICAL / THIS
   MISSION'S RIG** 明确标注。
8. **10 份 cpu_only_closure 文档**（00–09 + 本报告）+ `POST_ARM_A_SAFE_
   SWITCHOVER.md` 四门禁方案（A 实验真结束 / B 冻结 / C 新驱动测试 / D
   后续任务——当前一概不执行）。

## 2. 为什么修复（原始缺陷 → 真实风险）

| 缺陷 | 风险 |
|---|---|
| 旧 guard 只扫 evidence/ 的 json/jsonl、按 key 名 | 歌词换个 key 名/扩展名/目录即绕过；公开仓库持续暴露版权文本 |
| 无数值完整性程序化验证 | 脱敏若 silently 改数，科学证据链断裂且无人发现 |
| journal 测试靠字符串断言 | 崩溃恢复声称可靠但从未被真实崩溃检验——384 候选 campaign 的断点正确性悬空 |
| fixture 缺 identity（CI 从未真跑该文件） | 验证器的反伪造能力（identity recheck）无负向对照，"audit FULL"的可信度有洞 |
| 空 freeze 收据标进 G1 | 三环境可复现性声明无证据支撑 |
| README 历史混排 | 读者把上次 384/384 当成本次——mission 明令禁止的混淆 |

## 3. 如何证明（原始失败→根因→修复→对照→回归→CI）

见 `07_CI_AND_REGRESSION_RESULTS.md` 修复链表（6 行，每行含 Before/负向
对照/回归位置）；CI 证据：runs 43682957300 / 43682960115 双 success。
泄漏矩阵、数值对账、故障注入均为**真实执行**输出，非推演。

## 4. 对开发者的价值

- **可复现性**：三环境依赖收据齐备+fail-closed 校验，任何人可对账。
- **数据可靠性**：数值收据与原件逐叶对账；脱敏不再等于"信不信由你"。
- **断点续跑**：真实崩溃注入下的 journal 契约（不虚假计数/不丢记录/不埋
  腐败）首次有机器证明。
- **科学统计**：PER 选择必须用官方 selected_candidates、总体显式分离、
  互斥分组守恒、PER=1≠空——发表数字的每个分母可审计。
- **安全公开**：公开树歌词泄漏面=0（双 tier 矩阵证明），且 CI 持续拦截
  再提交。
- **协作**：PR #7/#8/#9/#10 关系定清（#8 可 Superseded，证据齐），Owner
  决策面从"读四个 PR"缩到"读一份矩阵+一份 GO/NO-GO 台账"。

## 5. Arm A 是否受影响

- 未执行任何 GPU 命令；未改运行目录（`/workspace/YuE2-SGLang-ROCm` 与
  `/data/yue2-runs/armA_wsb_full`）任何文件；未停/启任何进程；未动
  run_config/journal/音频。
- **只读状态证据**（2026-11-15T05:57:35Z）：驱动 16537 ALIVE，
  journal verified complete = **26/384**，0 failed，磁盘 1.5T 余。
- 本 Mission 的全部工作在独立 clone `/workspace/YuE2-CPU-Audit`。

## 6. 还有什么没完成

**A. CPU-only blockers**：无遗留（本次范围全闭环）。
**B. W7900-dependent**：Arm A 完成+审计+打分；Arm B 复现；AR Hang 根因；
HIP fault 复现；close() 调查；磁盘不足真实注入。
**C. 第三方评测依赖**：官方 vLLM 参考环境/作者的 per-song 收据（PER 因果
归因的最终对照）。
**D. Owner 授权依赖**：PR #7 合并（GO/NO-GO 台账已备）；LQ-1 历史处置
（A/B/C 方案已备）；上游 0010 等提交审批；受限音频打包权利确认。

## 7. 下一步（优先级/仓库/硬件/输入/验收/是否影响 Arm A）

| # | 任务 | 仓库 | 硬件 | 输入条件 | 验收标准 | 影响 Arm A? |
|---|---|---|---|---|---|---|
| 1 | Arm A 继续运行至 384 | 本仓库 | W7900（已占用） | 无（进行中） | audit FULL + 四指标 | 就是本体 |
| 2 | PR #7 合并决策 | 本仓库→main | 无 | Owner 读 06 台账 | 正常合并，无历史改写 | 无 |
| 3 | 打分链（Gate D 前置=A/B/C） | 本仓库 | W7900 | Arm A 完成 | 官方 summary+CI 收据 | 排队其后 |
| 4 | Arm B 复现 | 本仓库+SGLang | W7900 | 打分完 | 384/384 FULL+四指标 | 无 |
| 5 | PER 跨评测器包（权利确认后） | 本仓库 | CUDA 主机（外部） | Owner 授权音频打包 | 对照报告（不预设结论） | 无 |
| 6 | 上游 0010 提交 | WildSongBench | 无 | Arm A 官方打分证据+Owner 批 | 上游 PR | 无 |

## 8. 结论

C1 成功标准逐条核验：CPU 缺陷真修（6 链全闭环）✓ / 公开树零歌词
（双 tier 矩阵）✓ / PER·身份·日志·科学声明正确（测试+工具证明）✓ /
PR 关系无未识别冲突（矩阵+语义标记）✓ / CI 全绿（双 run）✓ / Arm A
未受扰（只读证据）✓ / 切换方案可执行（四门禁）✓ / 中文报告本文件 ✓。
未执行项（GPU/上游/历史改写）全部保持 BLOCKED/NOT_TESTED，无一项因
未执行而被判失败，也无一项被虚报完成。
