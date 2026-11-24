# RC5 阶段性状态（供审阅，非最终报告）

快照时间：2026-11-24T07:47:56Z。**本文件是进行中的快照**，最终结论以 `FINAL_REPORT_ZH.md` 为准。
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

## 关键发现

1. **最新上游逐比特复现历史生成**：12/12 pilot 候选的 `audio.flac` SHA256 与历史 Arm B 冻结清单完全相同（`03_PILOT_VS_HISTORICAL_MANIFEST.json`）。上游增量（2a816358 能力门控）只改 dispatch，不改 ROCm 上的输出。
2. **PER 差距的形态**（pilot，batch=1，4 次重复完全确定，micro 0.665；zh 0.232 / en 0.813）：英文歌出现两种失败——**空转写**（只出语言头即停，PER=1.0）与**跑满 4096 token 上限**。历史上 PER=1.0 的 prompt 86 在 batch=1 下同样空转写，因此**不是批量 padding 造成**。
3. **官方配置 PER 在本引擎上很贵**：batch 8 时每步 118 ms（batch 1 为 33 ms），整批要等最长序列；估计全量 384 首需 15–25 GPU 小时。
4. **上游新问题**（未擅自修补，已写入手 off）：导出 WAV 为 PCM_16（官方为 24-bit）；HTTP 计时字段恒为 null；2 个上游测试隐含非 ROCm 宿主假设。

## 进行中

- **M4 全量生成**：run_id `rc5_armB_latest_upstream_20261124T065451Z`，06:54:51Z 启动，快照时已完成 10/384。按 pilot 外推约 35 小时。
- **M6 PER 根因**：E4（独立参照 ASR）与 E2（ROCm vLLM）工具已写，待 GPU 空闲。
- **M7 Q3O**：显存预算已算（仅 Thinker 即 58 GiB > 可用 44.6 GiB）；HF 适配 judge 已写并通过官方协议检查；官方 key 环境已装并验证；待真机试跑。

## 未开始

M5 全量官方评分、M5 选样审计、M6 受控实验矩阵与最终判定、M7 逐级 pilot 与全量、M8 独立复审与 Release Gates、M9 最终报告。

## 已知限制

- 本快照中的 pilot 指标是 **12 个未选样候选**（刻意含高 PER 样本），不可与 selected-192 的论文/作者参考值比较。
- pilot 的 PER 使用 batch_size=1（时间受限的 pilot 变体）；官方 batch 8 配置的 PER 将在全量生成后对 384 首执行。
- 无 NVIDIA 硬件：CUDA fast-path 只有代码审阅与 CPU dispatch 测试，物理回归 NOT_RUN。
- 官方 ROCm vLLM wheel 索引被本机出口代理拦截。
