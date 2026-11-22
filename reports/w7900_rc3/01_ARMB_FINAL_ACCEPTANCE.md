# 01 — Arm B 最终物理验收（W7900-RC3）

**结论先行：Arm B 真实完成。384/384 候选、FULL 审计（本会话独立重跑确认）、
官方冻结评测器四指标打分完成（rc=0、complete=true、384+192 receipts）、
选样与聚合独立复算一致、provenance 0 违规。**

## 1. 验收目标逐项裁定

| 目标 | 要求 | 实测 | 裁定 |
|---|---|---|---|
| 唯一候选 ID | 384 | 384（manifest 重算，0 重复） | PASS |
| 完成候选 | 384 verified complete | 384（0 missing/invalid） | PASS |
| 缺失 ID | 0 | 0 | PASS |
| 重复最终 ID | 0 | 0（songs/ 目录亦无越界目录） | PASS |
| 无效 artifact bundle | 0 | 0（官方 verify_result 全过） | PASS |
| prompt 覆盖 | 192 prompts × {r0,r1} | 192（索引 0–191） | PASS |
| 官方种子公式 | 831001+i / 831019+i | 384/384 精确匹配（含 request.json 内部） | PASS |
| 模型/VAE/数据集 revision | 冻结 pin | YuE2-3B@1a96eca6 / Vae-legacy@b54118f0 / WSB@e361b85a | PASS |
| 评测器身份 | 冻结束 | 104/104 代码文件 + 116 资产哈希与两臂 protocol.json 完全一致 | PASS |
| audit.verdict | FULL | FULL（chain 产物 + 本会话独立重跑逐字节一致） | PASS |
| verify_provenance | 0 violations | 0 violations；384 LEGACY 如实标注（未升级为 VERIFIED） | PASS |
| 打分 rc / complete | 0 / true | per+songbench：rc=0 complete=true（384 receipts）；mulan+amc：rc=0 complete=true（192 receipts） | PASS |
| 截断候选 | 协议允许 | 5 个 truncated-but-complete（ASR cap 语义按官方 termination_policy 保留，不排除） | PASS（协议内） |
| 重试/失败 | 如实 | 生成期 0 retry / 0 fail（resumed=0） | PASS |

## 2. 独立复核方法（不信任 summary 的部分）

1. **生成完整性**：从 `generation_manifest.jsonl` 自底向上重算唯一 ID、prompt 覆盖、
   种子公式、状态分布；从 `evaluation_inputs.json` 重建期望集比对 songs/ 目录。
2. **输入身份链**：384/384 评测用 mp3 逐文件 sha256 与 `scores/audio_manifest.jsonl`
   一致；additional（mulan/amc）192/192 一致；selected-192 的 audio_sha256 是
   384 全集的真子集。
3. **选样复算**：按官方「(PER, edits, |Δphonemes|, repeat) / candidate_index」语义独立
   重算 best-of-2——micro/macro/未选样 PER、phonemes、edits、ASR cap 计数**全部与
   官方 summary 精确一致**。192 prompt 中 191 个选择逐字节相同；1 个（prompt 19）
   为 PER 完全并列（0.226013）时的 tie-break 差异（官方取 r1，独立复算取 r0），
   聚合不受影响（PER 相等）。MuLan/AMC 的 selected 集与 PER selected 集完全相同。
4. **聚合复算**：selected micro = edits/phonemes = 27 552/155 111 = 17.7628%；
   unselected micro = 24.4177%；zh/en 分层与官方一致。
5. **确定性/一致性**：两臂打分共享同一冻结评测器束（代码+资产哈希一致），
   protocol config 一致；generation_conditions 字段差异见 §4。

## 3. 四指标结果（磁盘实测；详见 01_ARMB_METRICS.json）

| 指标（selected-192） | 官方 | Arm A（torch-eager） | **Arm B（SGLang）** | B−官方 |
|---|---:|---:|---:|---:|
| SongBench Global | 6.7316 | 6.7417 | **6.7383** | +0.0067 |
| MuLan | 0.5068 | 0.4970 | **0.5092** | +0.0024 |
| AllMusicCaps | 0.4054 | 0.4010 | **0.4056** | +0.0002 |
| PER micro | 8.44% | 16.83% | **17.76%**（CI95 [15.22, 20.63]，prompt bootstrap n=10 000，seed 20261122） | +9.32 pp |
| PER（384 未选样） | — | 24.39% | **24.42%** | — |

非 ASR 三指标与官方差 ≤0.007 / ≤0.005 相对量级；PER 显著偏高（科学定性见 02 系列，
维持 PER_PARITY_OPEN，不在本验收内消化）。

## 4. Arm A / Arm B 科学一致性（M1.5）

**前提差异（明示）**：两臂为同一 GPU 上的两条独立实现路径——
Arm A = torch-eager 驱动（torch 2.10.0+rocm7.1，cfg_negative=same_instruction_and_exact_abc，
memory_budget 24 GiB）；Arm B = SGLang 服务（sglang ced0ef7d，torch 2.12.0+rocm7.14.1）。
同种子同 prompt 同模型/VAE/数据集 revision。

| 一致性检验 | 结果 |
|---|---|
| 配对差（B−A，per-prompt selected PER） | **−0.016 pp，CI95 [−1.759, +1.561] pp（含 0）→ 无统计显著差异** |
| Per-prompt Spearman ρ | 0.871（强正相关） |
| zh / en 分层 | A: 16.49/16.61%；B: 16.61/16.45%（组内一致） |
| 样本守恒 | 两臂均 384 候选 / 192 prompt / 零排除 |
| ASR cap | A: sel 36 / all 120*；B: sel 60 / all 120（*A 的审计器截断计数受 schema 缺陷影响，见 03 审阅——生成级截断 A=0/50 抽查） |
| 生成时长分布 | A mean 223.7s / B 220.8s（中位 217.1/217.2） |
| 同种子确定性 | RC3 pilot 同种子重生成 wsb_000_r0：identity 与 audio_seconds **逐位一致**（570c5ce9…/185.8787s） |

**读法**：两条实现路径（不同 torch/ROCm、不同 serving 栈）在同一 GPU 上复现出
统计上不可区分的 PER（≈16.8–17.8%）并同样复现官方非 ASR 三指标——
「ROCm 侧系统性 ~+9pp PER」是跨实现稳定现象，非单栈偶发。

## 5. 残留限制（如实）

1. PER 与官方的差距未闭合（因果矩阵与 handoff 见 02 系列；A2/B2/C1/C2 外部阻塞）。
2. provenance 全部为 LEGACY 级（诚实标注），非完整 source-provenance 链——
   身份由审计器对 384/384 重验证（request/config/weights identity 重算一致）。
3. Arm A 审计器的 truncated_but_complete=384 为 schema 计数缺陷所致的虚高
   （dict{abc,semantic} 全 False 被计 truthy）；已在 PR #16 修复并加回归测试；
   不影响两臂 verdict（均 FULL）与四指标。
4. Q3O 未测（48 GiB < 官方判官需求，范围决定待 owner+作者——沿用 RC2 状态）。
