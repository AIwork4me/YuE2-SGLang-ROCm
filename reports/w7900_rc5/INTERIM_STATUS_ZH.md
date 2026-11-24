# RC5 阶段性状态（供审阅，非最终报告）

快照时间：2026-11-24T13:47:00Z。**本文件是进行中的快照**，最终结论以 `FINAL_REPORT_ZH.md` 为准。
尚未完成的项一律如实标注，不以计划或推测代替结果。

## 已完成

| 阶段 | 结论 | 证据 |
|---|---|---|
| M0 硬件与环境 | W7900D / gfx1100 / 47.98 GiB / BDF 0000:03:00.0，身份链闭合；fp32/bf16 matmul 与 SDPA 实算通过 | `00_ENVIRONMENT.json` |
| M0 异机备份 | **BLOCKED**： owner 确认无备份机。已实现并演练的是“同机第二卷”级别（12/12 候选、132 个文件哈希一致） | `00_STORAGE_AND_BACKUP_PLAN.md`、`00_RECOVERY_DRILL.json` |
| M1 P0 锁生命周期 | RC4.1 缺陷确定性复现（5.96 s 窗口 × 47 采样）→ 单进程监督器修复 → 0 窗口 | `01_LOCK_RACE_REPRO.json`、`01_RC42_INDEPENDENT_REVIEW.md` |
| M1 P1 探针硬超时 / 就绪语义 / 物理身份绑定 | 三项关闭；真机就绪控制 6/6，真机身份负向控制 2/2 | `01_P0_P1_CLOSURE.json`、`01_REAL_GPU_*.json` |
| M1 回归与变异 | 新增测试 99 项；变异 38/38 KILLED（首轮 3 个存活暴露真实测试缺口，已补） | `01_NEGATIVE_CONTROL_MATRIX.csv`、`01_MUTATION_RESULTS.json` |
| M2 最新上游 | PR #42106 head `c67d541a` 冻结；仅 2 个导入守卫补丁（6 文件）即可原生运行；有效源码树哈希已记录 | `02_UPSTREAM_DELTA_REVIEW.md`、`02_PATCH_RECONCILIATION.csv`、`02_EFFECTIVE_RUNTIME_MANIFEST.json`、`02_CAPABILITY_MATRIX.json` |
| M3 Pilot | 预登记 6 prompt × 2 = 12/12，严格审计 PILOT，官方 prepare_inputs 12/12 | `03_PILOT_SELECTION.json`、`03_PILOT_ACCEPTANCE.json` |
| M7 Q3O MoE 放置块 | 两个替换 HF 循环的 MoE 块（GPU 批量 GEMM + CPU 常驻 fp32）；与逐字 HF 参考循环等价（无边界并列输入下偏差 ≤2 bf16 ulp，两种 torch 版本数字一致）；9 项测试 × 4 环境；变异矩阵 GPU 上 15/16 KILLED（唯一存活者为“舍入位置”近等价变异，已披露） | `07_Q3O_MOE_EQUIVALENCE.json`、`tests/test_rc5_q3o_moe.py`、`scripts/mutation_controls_q3o_moe.py` |

## 关键发现

1. **最新上游逐比特复现历史生成**：12/12 pilot 候选的 `audio.flac` SHA256 与历史 Arm B 冻结清单完全相同（`03_PILOT_VS_HISTORICAL_MANIFEST.json`）。上游增量（2a816358 能力门控）只改 dispatch，不改 ROCm 上的输出。
2. **PER 差距的形态**（pilot，batch=1，4 次重复完全确定，micro 0.665；zh 0.232 / en 0.813）：英文歌出现两种失败——**空转写**（只出语言头即停，PER=1.0）与**跑满 4096 token 上限**。历史上 PER=1.0 的 prompt 86 在 batch=1 下同样空转写，因此**不是批量 padding 造成**。
3. **官方配置 PER 在本引擎上很贵**：batch 8 时每步 118 ms（batch 1 为 33 ms），整批要等最长序列；估计全量 384 首需 15–25 GPU 小时。
4. **上游新问题**（未擅自修补，已写入手 off）：导出 WAV 为 PCM_16（官方为 24-bit）；HTTP 计时字段恒为 null；2 个上游测试隐含非 ROCm 宿主假设。
5. **torch 2.10.0+rocm7.14.1 的 `torch.topk` 并列处理不稳定**（评估 venv，W7900D）：router logits 是 bf16 值，并列常见；当并列落在 top-k 边界时，同一输入重复调用会选出**不同的专家**（torch 2.12.0 上跨调用稳定，但仍与 CPU 不同）。HF 官方 MoE 循环用的就是 `torch.topk`，因此在该 torch 版本上构建的贪婪 judge **不可复现**。两个 MoE 块已改用稳定 argsort（并列取最小专家下标）；官方 vLLM 核的并列规则在本机不可知，**并列输入下的等价性不作声明**。实测数据见 `07_Q3O_MOE_EQUIVALENCE.json`。
6. **48 GB 上 Q3O 可行**（保留的那次试跑）：Thinker 34 层 GPU + 14 层 CPU 常驻 fp32，加载 152 s，单首 176 s（prefill 69 s + 487 token × 0.214 s）；VRAM 峰值 43.1 GiB，宿主峰值 50.1 GiB（cgroup 限 55 GiB，余量仅 4.9 GiB——不可再增加 CPU 层数）。该次得分 4.83；另两种放置的单次观察（5.0 / 4.83）**原始工件未保留**（被后续运行覆盖，已披露），且当时 CPU 块确有两处偏离官方舍入点（已修复并有回归测试）。

## 进行中

- **M4 全量生成**：run_id `rc5_armB_latest_upstream_20261124T065451Z`，**主动暂停在 20/384**（为 Q3O/PER 实验让出 GPU；退出码 143、清理 CLEAN、锁已释放）。检查点 16 已写入并验证到第二卷备份；**候选 17–20 尚未进入备份**。按已完成的 20 首外推，剩余约 28 小时。快照：`04_CAMPAIGN_PAUSE_SNAPSHOT.json`。
- **M6 PER 根因**：E4（独立参照 ASR）与 E2（ROCm vLLM）工具已写，待 GPU 空闲；E1/E4 证据见 `06_PER_CAUSAL_PILOT.json`。
- **M7 Q3O**：judge 修复已落地（线程配额、EOS、设备审计、稳定 top-k、舍入点修复、批量 GPU 块）；**批量 GPU 块尚未在真实候选上运行**；修复后 judge 的运行间稳定性未测。

## 未开始

M5 全量官方评分、M5 选样审计、M6 受控实验矩阵与最终判定、M7 修复后重测 + 逐级 pilot + 全量、M8 独立复审与 Release Gates、M9 最终报告。

## 已知限制

- 本快照中的 pilot 指标是 **12 个未选样候选**（刻意含高 PER 样本），不可与 selected-192 的论文/作者参考值比较。
- pilot 的 PER 使用 batch_size=1（时间受限的 pilot 变体）；官方 batch 8 配置的 PER 将在全量生成后对 384 首执行。
- **Q3O judge 的数值未与官方 vLLM/CUDA 对齐**（无从对齐）：单次试跑显示输出对放置/数值敏感（434/493/487 token，5.0/4.83/4.83），其中多少来自当时的 topk 非确定性、多少来自放置差异**未分离**；修复后的运行间稳定性待测。
- Q3O 三种放置中的两种**原始工件未保留**（输出目录与日志被覆盖；数字来自操作员记录，已在证据中标注）。
- 保留试跑的 runtime receipt 中 "official bf16 rounding points" 表述**不准确**（当时 CPU 块的 router logits 未舍入到 bf16、silu 输出未舍入）；已在 `07_Q3O_48GB_PILOT.json` 更正，代码已修复。
- 无 NVIDIA 硬件：CUDA fast-path 只有代码审阅与 CPU dispatch 测试，物理回归 NOT_RUN。
- 官方 ROCm vLLM wheel 索引被本机出口代理拦截（E3/E7 只能通过 hand-off 包在 CUDA 机上做）。
