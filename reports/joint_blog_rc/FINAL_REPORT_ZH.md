# FINAL_REPORT_ZH — YUE2-AMD-JOINT-BLOG-RC（中期快照 2026-11-19T02:15Z）

> **本文件为持续任务的中期状态报告。** Arm B 物理战役仍在运行（预计
> 2026-11-20T23:00Z 完成），M4/M5 的 GPU 窗口排在其后，作者协作尚未发出。
> 最终裁定将在所有关卡 receipts 齐备后更新；本版如实反映当前证据状态。

## A. 执行裁定（当前）

**`JOINT_BLOG_NO_GO`（截至本快照）**

理由（逐项可验证）：
- R1 集成 RC 的 CPU CI：**PASS**（PR #15 run 44438397629：327 passed / 0 failed / 28 skipped；本地清单机 355/0/0）
- R2 Arm A 官方全量基准：**PASS**（384/384，audit FULL，四指标 receipts 齐备）
- R3 Arm B 官方全量基准：**IN_PROGRESS**（验收 PASS（含真实生成 33.1 s 音频）；战役 armB_full_20261119T015756Z 运行中，1/384 @ 02:06Z）
- R4 PER 差异科学闭合：**OPEN/BLOCKED_EXTERNAL**（A2/B2/C1/C2 跨评测器单元待作者/CUDA 侧；内部证据收敛于 ROCm ASR 后端为首要嫌疑，见 03 报告）
- R5 运行时可靠性：**PARTIAL/NOT_TESTED**（历史 RCA 在案；新鲜映像复验排在战役后）
- R6 官方指标与基准范围：**PARTIAL**（SongBench/MuLan/AMC 达标复现；PER 未达；Q3O NOT_TESTED——48 GB 低于官方裁判需求，范围缩减需作者+AMD 同意）
- R7 安全/许可/溯源：**PASS**（tier-1+tier-2 真实数据扫描 0 泄漏；溯源链 0 违规；历史 Git 对象残留为已记录的 owner 决策项）
- R8 独立复现：**NOT_TESTED**（M8.1 清单就绪，待战役后干净工作区执行）
- R9 作者科学批准：**NOT_PRESENT**（请求已备好，未发送，绝不虚称）
- R10 AMD 出版批准：**NOT_PRESENT**

## B. 仓库与 PR 状态

| 项 | 值 |
|---|---|
| 初始 HEAD | `f7fda39`（PR #13；即活动战役检出） |
| 实况树现 HEAD | `fee027d`（owner 授权 ff 到 PR #14 head；监督进程未受扰动，验收即通过） |
| 工程分支 | `mission/joint-blog-rc-m1`（PR #14，Draft）；`integration/joint-blog-rc`（PR #15，Draft，= #14 + #12 栈合并 + #8 调和 + #7 文档恢复） |
| CI | PR #14 run 44433225686 **164/0/26**；PR #15 run 44438397629 **327/0/28** |
| PR 建议 | #8 可按"被取代"关闭（其语义已移植为测试）；#10/#11/#12 已并入 #15 |
| 未合并 main | 遵守规则；等待 owner 审查 |

## C. 物理硬件证据

- GPU：**AMD Radeon Pro W7900D**（W7900 级变体；PCI `03:00.0`，device `0x744b`，subsystem `0x0e0c`，SKU `D7070910`；gfx1100，96 CU，VRAM 47.98 GiB）——命名保留，未"归并为 W7900"
- 驱动/栈：amdgpu 6.16.13；宿主 ROCm 7.2.1（未改动）；各环境自带 torch 2.12.0+rocm7.14.1 轮子
- 战役身份：Arm A `armA_full_20261115f`（模型 rev `1a96eca6`，VAE rev `b54118f0`，协议锁 frozen 2026-11-11）；Arm B `armB_full_20261119T015756Z`
- 归档 SHA256：`45e7c0f9…` 重算一致
- 验收 receipts：`/data/yue2/logs/armB_acceptance/acceptance_receipt.json`（33.079 s @48 kHz，RMS 0.1486，sha256）

## D. 官方指标对照（selected-192）

| 指标 | 官方参考 | AMD 实测（本映像 Arm A） | 差值 | 协议兼容 | 阈值 | 裁定 | 证据 |
|---|---:|---:|---:|---|---|---|---|
| SongBench GA ↑ | 6.7316 | 6.7044 | −0.0272 | 是 | ±0.05 | **PASS** | scores/summary.json |
| MuLan ↑ | 0.5068 | 0.4970 | −0.0098 | 是 | ±0.01 | **PASS**（贴边） | additional/summary.json |
| AllMusicCaps ↑ | 0.4054 | 0.4010 | −0.0044 | 是 | ±0.01 | **PASS** | additional/summary.json |
| **PER ↓** | 8.44 % | **16.83 %** [14.87–18.92] | **+8.39 pp** | 是（同一冻结协议/评测器） | ±2 pp（暂定） | **FAIL（开放调查）** | 03_PER_CAUSAL_ANALYSIS.md |
| **Q3O ↑** | 4.6819 | 未测 | — | — | — | **NOT_TESTED**（48 GB < 官方裁判需求；范围缩减待作者+AMD 同意） | — |

（Arm B 本映像四指标待战役完成；换机前 Arm B 历史：SB 6.7376 / MuLan 0.5093 / AMC 0.4056 / PER 17.77 %——独立世代，另行标注。）

## E. 根因台账（本次会话新闭合的缺陷）

| 症状 | 复现 | 根因 | 修复 | 回归 |
|---|---|---|---|---|
| CI 5×TestScoreGate PermissionError '/data' | CI run 44421080608 | gpu_lock.DEFAULT_LOCK 导入期冻结 + score() 用全局默认 | 调用期解析 + 依赖注入 + 锁超时=门 FAIL | 3 新测试 + CI 164/0/26 |
| armB 验收死循环（30 min/次） | 实况 23:55Z 尝试 | ①LOG 环境变量名冲突（目录≠文件）②trap 被 exec 丢弃 ③--run-state 传文件应为目录 ④RUN_ID 未导出（--run-id ""）⑤轮询间隔≥超时 | serve 改 SERVER_LOG；启动器保留 trap + 信号转发；RECEIPT_DIR；导出 RUN_ID；ARMB_HEALTH_POLL_S | 16 场景真子进程测试全绿；实况验收 01:55Z PASS |
| 验收无真实生成 | 评审发现 | /health+/v1/models 不构成生成验收 | armb_acceptance_request.py（有界、非协议冒烟参数明示、音频可解码/≥5 s/非静音、sha256 receipt） | 实况 33.1 s 音频 receipt |
| 归档恢复缺少强制哈希/崩溃安全 | 分析 | 校验靠人；解压直写目标目录 | --expect-sha256 强制（exit 6）+ 暂存原子改名 + 保留失败现场 | 10 测试全绿 |
| 18 个休眠测试缺陷 | 本地主清单机首次全量运行 | 仅在有清单主机可运行；从未在 CI 执行 | 工作区传播/自洽身份束/断言词表 | 190→355 全绿 |

## F. 科学诚信分类

- **实测证据**：本映像 Arm A 384 全链 + 四指标；验收生成；跨臂配对分析；溯源/安全扫描
- **历史证据**：换机前 Arm B（17.77 % 等）、gfx1151（17.22 % 重算）、10 月 SGLang——各自世代，绝不混用
- **同音频对照**：A1/B1/G1 已测；A2/B2/C1/C2 **BLOCKED_EXTERNAL**（工具包就绪）
- **未检验假设**：H1/H2 终裁待跨评测器；AR hang 根因；HIP IMA 归属；close() 内存上游语义

## G. 剩余工作（按关键路径）

| 优先 | 项 | 阻塞点 | 责任 | 验收条件 |
|---|---|---|---|---|
| P0 | Arm B 384/384 + audit + 四指标 | 战役运行（ETA 11-20T23Z） | 无人值守（监督链自管） | 02_M2 全 PASS |
| P0 | R4 PER 闭合 | EXT-1/2/3（作者/CUDA 侧） | owner 发送请求 + 作者 | A2/B2 或 C1/C2 执行且结论落档 |
| P0 | M4 运行时 RCA（AR hang/HIP/close()） | 战役后 GPU 窗口 | 本会话/后续会话 | 04 报告 + 支撑实验 |
| P1 | M5 性能表征 + 指标矩阵 | 战役后 GPU 窗口 | 同上 | 05 系列 |
| P1 | M8.1 干净复现 | 战役后 | 独立工程师 | 08_FINAL_INDEPENDENT_REVIEW |
| P1 | 作者/AMD 审查 | 外部 | owner | R9/R10 真实批准 |
| - | 历史 Git 对象处置 | owner 决策（建议本 RC 接受残留+记录） | owner | M6 备注闭环 |

## H. 最终发布建议（当前）

**联合博客暂不具备发布条件（NO_GO）**；最小关键路径 =
Arm B 完成（自动）→ M4/M5 GPU 窗口 → EXT-1/2/3 作者协作 → M8.1 独立复现
→ 作者+AMD 审查。除外部依赖外，全部路径上的工程与证据工作均已就绪
或已在执行。

## 持续运行交接（§12 合规）

- 最后完成关卡：P0 GO；M1 工程 PASS（待 owner 审查 PR #14/#15）；M2 Arm A PASS、Arm B IN_PROGRESS；M3 内部分析完成（开放项=外部单元）；M6 PASS；M7 就绪未发
- 活动进程：mission_chain PID 3363794（state=armB_campaign）；Arm B 启动器树 PID 635532/635539/635541；sglang serve PID 635542；driver PID 636313
- GPU 所有权：gpu.lock=armB-campaign:armB_full_20261119T015756Z（合法持有）
- 已验证候选数：Arm B 1/384 @ 02:06Z（journal 重算，勿硬编码）
- 运行目录：/data/yue2-runs/armB_wsb_full；日志 /data/yue2/logs/armB_armB_full_20261119T015756Z.log
- 源 SHA：实况树 fee027d；工程树 integration/joint-blog-rc @ cf21ae2
- 恢复命令：无需人工干预（监督链自动推进）；若监督链死亡：`setsid nohup python3 /workspace/YuE2-SGLang-ROCm/scripts/campaign_ops/mission_chain.py >> /data/yue2/logs/mission_chain_console3.log 2>&1 &`
- 安全停机：`python scripts/gpu_lock.py stop --yes`（仅对持有者；随后驱动 SIGINT 优雅停止）
- 已知风险：AR 阶段挂起（watchdog 在役，~1/300 历史）；GPU 共享 HIP 故障（单租户策略在役）
- 阻塞依赖：EXT-1..6（见 07 包）
