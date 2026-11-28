# M4 — Q3O Difference RCA (Scoreboard B vs 官方论文参考)

数据（全部真实测量）：
- 论文参考 Q3O = 4.68/5（evaluator bundle README verified section；同源 H800 官方复现 4.69 original / 4.71 fresh）
- Scoreboard A（S_T，RC5.1 冻结）：4.393986
- **Scoreboard B（S_V，RC6.1 本轮）：4.342293**（192/192 valid · 132 复用 + 60 新评 · 0 失败 · 0 解析失败）
- B vs 论文残差 = **-0.337707**；B vs A = -0.051693

## 1. 可量化分解（已测）

| 因素 | 测量值 | 方法 |
|---|---|---|
| 1. Selection effect（选样效应） | **-0.051693** | Q3O(S_V) − Q3O(S_T)，同一 judge、同 132 共享候选 + 各 60 差异候选（官方 PER best-of-2 语义，未按 Q3O 挑选） |
| 2. Within-engine repeatability | 见 04_Q3O_REPEATABILITY.json（8 候选冻结子集 × 2 进程） | M4.5 |
| 3. 路由 tie 统计（S_V 全 192 收据实测） | GPU MoE 边界 tie 率均值 **23.11%**；CPU 21.60%；合并 22.35%（范围 0.176–0.268）；tie 率与分数相关系数 **0.008**（不相关） | 每收据 routing_tie_stats |
| 4. judge 实现敏感性（既有冻结证据） | mutation controls 15/16 KILLED（top-k 归一化、tie-break 稳定性、bf16 路由前舍入等逐点钉死） | rc5_1/02_Q3O_MOE_MUTATION_GPU.json |

解释：修正 PER 选样（S_V）相比冻结选样（S_T）选出的候选集在 Q3O 上低 0.052 —— 这是**选样集合差异**，不是 judge 差异。两臂共享的 132 候选分数逐字节复用（身份核验后）；差异全部来自各自独有的 60 候选。

## 2. 已知实现差异（披露，不归因为主因）

- 引擎：HF transformers 4.57.6 SDPA-ROCm vs 官方 vLLM 0.14.0 + FlashAttention 2.8.3 CUDA
- MoE tie-break：本方 lowest-expert-index 稳定规则 vs 官方 fused kernel 未公开规则；~22% 路由槽为精确并列（tie 率与分数不相关 → 聚合影响小，但逐 token 专家选择不保证等价）
- 累加 dtype：GPU bf16 逐专家 index_add vs 官方 fused kernel fp32 累加（RC5.1 已披露）
- CPU 14 层 fp32 算术 + 披露的 bf16 舍入点

## 3. 未闭合项（OPEN，诚实标注）

- **官方 judge 与本 judge 的同音频分数差**：无 CUDA host —— `Q3O_OFFICIAL_EQUIVALENCE_NOT_ESTABLISHED`。比较器与预注册判据 runbook 已就绪（author/CUDA_Q3O_RUNBOOK.md）。
- **生成本身的质量差**（我们的 W7900 fresh generation vs 论文 original audio）：H800 数据点（4.69 original / 4.71 fresh）表明官方 judge 上两种音频接近；我们的 4.34 在无官方 judge 时无法把「生成质量」与「judge 实现」分开。
- **-0.3377 残差的归因比例**：选择效应已测（-0.052）；其余 -0.286 与 RC5.1 在 S_T 上的残差（4.393986 − 4.68 = -0.2860）一致 —— 即残差几乎全部来自「judge 实现 + 生成本身」的复合，无法在无 CUDA 时进一步分解。

## 4. 反纪律检查（未发生）

- 未用 4.68 作目标函数；未调 temperature/judge prompt/解析规则；未删低分候选；未取 best-of-N；未事后放宽容差。选样保持官方 PER 语义（严禁按 Q3O 挑选——04_Q3O_CORRECTED_SELECTION_MANIFEST.json 的 selection_identity 逐候选绑定 PER 选样数据）。
- M4.8 有界数值实验未新增本轮：RC5.1 已完成的 mutation controls + 本轮 2 进程 repeatability + 192 收据 tie 统计覆盖了同一预算内的全部可测量；routing oracle / 逐层 CPU-GPU 对照需要 CUDA 参照（BLOCKED_EXTERNAL），预注册判据已在 runbook 冻结。
