# FINAL_REPORT_ZH — YUE2-AMD-JOINT-BLOG-RC2（2026-11-19T05:00Z 快照）

> **持续任务中期报告。** Arm B 物理战役仍在运行（35/384 @ 04:47Z，
> 预计 2026-11-20T23:00Z 前后完成生成），M4/M5 GPU 窗口排在其后，
> 作者协作包已备好但未发送。最终裁定在所有关卡 receipts 齐备后更新。

## A. 执行裁定（当前）

**`JOINT_BLOG_NO_GO`（截至本快照）** —— 与 RC1 中期快照一致；但 G1/G7
两项取得实质性进展（G1 由 RC2 评审分支补齐条件，G7 本会话复查通过），
且发现了并修复了 2 个 P1 级工程缺陷。无任何关卡被静默放宽。

## B. 精确 Git 状态

| 项 | 值 |
|---|---|
| 会话初始 | 活动战役检出 `fee027d`（PR #14 head，未触碰）；评审基线 `66b5a13`（PR #15 head） |
| 会话最终（工程分支） | `mission/joint-blog-rc2` @ `16cd217`（= PR #15 + 2 个 RC2 提交），已推送 |
| Draft PR | **#16**（base=integration/joint-blog-rc）：修复 + 18 个回归测试；**CI 绿**（run 44458329312；首提交 run 44458302450 亦绿） |
| PR #8–#15 | 全部 OPEN/Draft/MERGEABLE（实况核对）；处置建议见 RC2_01b；未关闭、未合并、未强推 |
| main | `ba99c4d`；PR #15 领先 119 / 落后 4（= PR #7 安全合并集，blob 级内容一致，见 RC2_00 §3） |
| CI 证据 | PR #15 run 44442680950 PASS（327/28）；本机单进程 CI 范围套件 **373/0**（355 基线 + 18 新测试） |

## C. W7900D 物理证据

- 硬件/驱动：gfx1100（W7900D 级，device 0x744b，48 GiB），ROCk 6.16.13，宿主 ROCm 7.2.1。
- **Arm B 战役（实况核验，四路交叉）**：run `armB_full_20261119T015756Z`，
  gpu.lock 由启动器网关持有（01:57:56Z 起）；监督链 PID 3363794 健康巡检
  （10 分钟节奏，driver_alive=True 每次通过）；35/384 全部 complete、
  0 重试、单候选 200–286 s；模型/VAE/数据集/补丁集/种子身份与冻结协议一致。
- 溯源兼容矩阵（RC2_00 §4）：Arm A 生成源 = `0dedd415`（驱动内容哈希
  d2b983c8 唯一命中）；Arm A 打分在 `f7fda39` + 冻结评测器束 `bd550b36`；
  Arm B 驱动 `run_wsb.py` 在 f7fda39/fee027d/66b5a13 **字节一致**
  （3d168c47）；生成/打分语义路径在证据源→PR #15 之间零变化 → **全部 PASS**。
- 本会话未对 GPU 执行任何工作负载；战役检出未改动。

## D. 科学结果

| 指标（selected-192） | 官方 | Arm A 本映像 | Arm B 本映像 | 状态 |
|---|---:|---:|---:|---|
| SongBench GA | 6.7316 | 6.7044 | *运行中* | PASS（Arm A） |
| MuLan | 0.5068 | 0.4970 | *运行中* | PASS |
| AllMusicCaps | 0.4054 | 0.4010 | *运行中* | PASS |
| **PER** | 8.44 % | **16.83 %** [14.87–18.92] | *运行中* | **FAIL / 开放** |
| Q3O | 4.6819 | 未测 | 未测 | NOT_TESTED（48 GB < 官方判官需求；范围缩减待定） |

PER 因果调查（RC2 增量，详见 rc2/RC2_03_*）：
- **新证据 E7（方向性）**：转录系统性偏短（净 −47.7 字符 [−70.3, −28.5]，
  140/50 负向）——错误以"漏读/欠转录"（deletion）为主，与 H1（ROCm ASR
  后端）方向一致，与"整体生成劣化"（非 ASR 判官全部持平）不一致。
- **新证据 E8**：PER 与歌长/词长/ASR 输出长度相关性弱（|ρ|≤0.13）→
  排除"长度伪影"假设（H8，新增）。
- **工具包审计（关键）**：旧 CUDA 交接工具 **不可执行**（`python -m`
  调用错误、mp3-only 载荷不足、布局不匹配、缺 prepare 步骤）。
  修正后的工具在本机通过官方冻结 `prepare_inputs()` **384/384 实证
  验证**，16.3 GiB 全束清单（4224 文件 SHA256）端到端校验通过，
  接收端防错校验器 4 种损坏模式全部拒收。
- 结论不变：**PER_PARITY_BLOCKED_EXTERNAL**（A2/B2/C1/C2 待外部执行；
  预注册判读表 8–11 % ⇒ H1 / 16–18 % ⇒ H2；±2 pp 暂定验收标准不变）。

## E. 运行时 RCA

本会话未获 GPU 窗口（战役优先）——M4.1 AR 挂起、M4.2 HIP IMA、M4.3
close() 内存：维持 **历史证据 + 预注册协议**（04 报告），无新根因声明。
**评审侧新增（代码级，非 GPU）**：`score()` 无超时（挂死评测器将永久
持有 GPU 锁）与无限重试 —— 已修复（YUE2_SCORE_TIMEOUT_S=6h 默认 +
YUE2_SCORE_MAX_ATTEMPTS=8 上限 + 证据保全 + blocked_reason 升级）；
audit/acceptance 超时不再击溃监督链。见 PR #16。

## F. 独立评审（RC2_01，AI 二审；不冒充人类批准）

- 方法：逐行评审 15 个运行时/溯源文件；精确 HEAD 单进程套件 373/0；
  预注册变异控制 5/5 杀灭 + **自建 16 个对抗变异**（11 被原套件杀灭，
  5 存活 → 全部由新测试钉死并复验杀灭 F1–F8）。
- 缺陷与修复（全部在 PR #16，CI 绿）：
  - **P1-1** 复活候选记作 `complete(resumed)`，链门计数不可见 →
    日志尾丢失恢复场景死循环（P1）；修复：精确 `complete`+resumed 标志
    （与 Arm A 驱动对齐）+ 前缀计数（向后兼容）。
  - **P1-2** 直连服务器测试套件默认开启（文档称 opt-in）→ 基准主机上
    `pytest tests/` 会向冻结战役服务器发送生成流量；修复：真 opt-in +
    gpu.lock 在持拒绝。**事件披露**：评审期间该缺陷致 ≤2 次 ≤7 分钟
    的测试接触（评审前修复不存在）；战役完整性逐项核验无影响
    （0 失败候选 / 0 重试 / 时长正常）。
  - P2/P3：评测器无界执行、无界重试、guard 词表/stop 复验/renameat2
    回退三项变异存活、磁盘守卫仅断内层、同秒 partial 目录碰撞、
    manifest 主机跨文件 sys.modules 污染（基线即存在，实证于 66b5a13）。
- PR #14+#12 组合问题：在合并树上验证（非描述层面）——两侧行为共存，
  冲突解决未丢失任一侧不变量；main 落后 4 提交为 PR #7 拓扑残余，
  blob 级一致。
- 接受度：rc2 分支合入后 **G1 条件满足**（零开放 P0/P1）。

## G. 作者协作

- 备好（未发送，G9 诚实保持 NOT_PRESENT）：`RC2_06_AUTHOR_MESSAGE_EN.md`
  （可发送稿 + 准确性清单：Arm B 如实标注运行中、传输量更正 16.3 GiB、
  无背书暗示）、行动项清单、上游贡献矩阵（RC2 修订）。
- 外发需 owner 授权门：venue 选择（WildSongBench issue vs 邮件）+
  私有传输通道决定（EXT-5）。本会话零外发。

## H. 发布关卡台账

| 关卡 | 验收 | 状态 |
|---|---|---|
| G1 | PR #15 工程评审 + 最终精确 HEAD CI | **CONDITIONAL** — 评审完成、缺陷已修于 PR #16（CI 绿）；待 owner 审阅合入 |
| G2 | Arm A 384/384 + 溯源 + 打分核验 | **PASS**（含 RC2 内容哈希级溯源确认） |
| G3 | Arm B 384/384 + 溯源 + 打分核验 | IN_PROGRESS（35/384；链自动推进至审计与四指标） |
| G4 | PER 平价科学闭合 | **BLOCKED_EXTERNAL**（工具已实证可用；A2/B2/C1/C2 待执行；±2 pp 标准冻结不变） |
| G5 | AR 挂起/HIP 故障/内存行为有发布安全结论 | NOT_TESTED（GPU 窗口排队；协议预注册） |
| G6 | 官方指标与性能范围接受 | PARTIAL（三指标达标复现；Q3O/性能未测；范围决定待 owner+作者） |
| G7 | 安全/许可/溯源 | **PASS**（RC2 会话产物复查 + M6 复核；历史 Git 对象 = owner 法律决策，显式开放） |
| G8 | 干净克隆复现 | NOT_TESTED（M8.1 清单与命令矩阵就绪：RC2_07） |
| G9 | 作者科学批准 | NOT_PRESENT（消息备好未发） |
| G10 | AMD 出版批准 | NOT_PRESENT |

## I. 剩余任务（优先级 / 阻塞 / 责任 / 验收）

| 优先 | 任务 | 阻塞 | 责任 | 验收 |
|---|---|---|---|---|
| P0 | Arm B 完成 → 审计 → 四指标 → RC2_02 闭合 | 战役运行（自动） | 无人值守 + 会话监控 | 384/384 FULL + 四指标 receipts + 配对分析 CSV/清单 |
| P0 | owner 审阅合入 PR #16（G1 收口） | owner | owner | 合并或附带修改后合入；最终 HEAD CI 绿 |
| P0 | 发送作者请求（含传输授权） | owner（venue + EXT-5） | owner | 实际外发 + 回应落档 |
| P0 | A2/B2 跨评测器执行 | CUDA 主机 + 授权 | 作者/志愿者主机 | 预注册判读落档；G4 收口 |
| P1 | M4 运行时 RCA（三缺陷） | 战役后 GPU 窗口 | 后续会话 | 04 报告 + 区分性实验 |
| P1 | M5 性能表征 | 同上 | 同上 | 05 系列（冻结方法执行） |
| P1 | M8.1 干净克隆复现 | 同上 | 独立执行者 | RC2_07 清单全绿 |
| P1 | Q3O 范围决定 | owner + 作者 | owner | 显式接受 NOT_TESTED 或 MI300X/作者侧交接 |
| - | 历史 Git 对象处置 | owner 法律决策 | owner | 三选一落档 |

## J. 最终建议（当前最小关键路径）

1. **（自动）** Arm B 战役完成 → 监督链自动审计与四指标打分。
2. **（owner，即刻可做）** 审阅合入 PR #16；授权并发送 RC2_06 作者消息
   与 16.3 GiB 私有传输。
3. **（外部）** 作者/CUDA 主机执行已验证的 A2/B2 工具 → G4 按预注册
   判读表收口（无论结果偏向 H1 还是 H2，均已承诺如实发表）。
4. **（GPU 窗口）** M4 三缺陷 RCA + M5 性能 + M8.1 干净克隆。
5. 作者科学批准（G9）→ AMD 技术批准（G10）→ 发布裁定更新。

## 持续运行交接（§12 合规）

- HEAD：战役检出 `fee027d`（勿动）；工程 `mission/joint-blog-rc2` @ `16cd217`（PR #16 Draft，CI 绿）。
- 活动进程：mission_chain PID 3363794（state=armB_campaign）；启动器树 635532/635539/635541；sglang serve 635542（:31000）；driver 636313。
- GPU 所有权：`/data/yue2/gpu.lock` = armB-campaign:armB_full_20261119T015756Z（合法）。
- 已验证候选：35/384 @ 04:47Z（journal 重算；勿硬编码）。
- 最后验证关卡：G2 PASS；G1 CONDITIONAL（PR #16 待合入）；G7 PASS。
- 恢复命令：监督链自愈；若链死亡：`setsid nohup python3 /workspace/YuE2-SGLang-ROCm/scripts/campaign_ops/mission_chain.py >> /data/yue2/logs/mission_chain_console3.log 2>&1 &`（注意：链在战役检出上运行——**先取得 owner 授权再考虑将 PR #16 快进至该树**，宜选稳定窗口）。
- 安全停机：`python scripts/server_identity.py stop --receipt /data/yue2/logs/armB_server_identity/server-identity.json --timeout 180`（仅验证身份；绝不 pkill）。
- 已知风险：AR 阶段挂起（~1/300 历史，watchdog 在役）；GPU 共享 HIP 故障（单租户策略在役）；评测器阶段现已有界（PR #16 前的树无此保障）。
- 阻塞依赖：EXT-1..6；PR #16 owner 审阅；Arm B 完成。
