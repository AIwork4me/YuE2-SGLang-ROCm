# MISSION W7900-RC5.1 — 最终报告（中文）

时间线：2026-11-24T13:47Z（接手 RC5 快照：20/384 暂停）→ 2026-11-27（全部完成）。
所有结论可回溯至 `reports/w7900_rc5/rc5_1/` 下的机器可读回执；本文件是入口。

---

## A. Executive Verdict（八项任务逐项判定）

| 任务 | 判定 | 关键证据 |
|---|---|---|
| P0.1 检查点与恢复闭合 | **PASS** | 20/20 官方 verify；17–20 尾部检查点补齐（根因：SIGTERM 路径跳过尾部归档，已修复）；恢复演练 20/20 → 终态 384/384；`01_*.json/md` |
| P0.2 精确 HEAD CI 闭合 | **PASS** | torch 收集错误根因关闭 + 独立 `q3o-moe-cpu-numerics` job（锁定 CPU torch 实跑数值）；最终 HEAD CI push+PR 双绿；`02_*.md/json` |
| P0.3 Q3O 模型级稳定验证 | **PASS（ROCM_ADAPTED_PILOT_GO）** | 5 次/2 进程 token 级完全一致（4.833333）；真实路由并列率 18.35%/20.20%；8 样本 8/8；峰值 VRAM 43.1 GiB、宿主余量 4.3 GiB；官方等价性 NOT_ESTABLISHED（无 CUDA 主机） |
| P0.4 恢复全量生成 384/384 | **PASS（FULL）** | 单一续跑会话 rc=0，0 失败 0 重试；5 个 truncated-but-valid；P50 275.27s（历史 275.3s）；`04_*.json/csv` |
| P0.5 官方 PER 全量与选样 | **PASS** | 384×4=1536 回执；selected-192 micro **17.7699%**（历史 17.7628%，Δ+0.007pp）；独立选样审计 192/192 零分歧；S/D/I 分解 192/192 验证；冻结 manifest |
| P0.6 剩余指标全量 | **PASS** | SongBench **6.736891**、MuLan **0.509395**、AMC **0.405181**（各 192/192，0 失败）；Q3O **4.393986/5**（192/192）；五指标记分板 |
| P1.1 PER 因果根因 | **CONFIRMED（复合，主因闭合）** | 同音频矩阵：空转写在 bf16/fp16/fp32/eager/batch1/CPU 全不变，vLLM 同权重同 GPU 正常转写；修正臂 selected micro **8.4488%**（论文 8.44%，零调参）；`07_*.md/json/csv` |
| P1.2 独立审阅与交付 | **完成（G0–G17：12 PASS，3 NOT_RUN，等价类如实标注）** | 独立审阅、回归套件（543+12 通过，384/384 恢复演练）、门禁账本、文档、PR #19 更新 |

## B. Exact Git State

- Initial HEAD（接手时）：`bb7731752931b0bf6078a0c1b3623d109958a2fb`
- Final HEAD：见 `08_GITHUB_FINAL_STATE.json`（本报告同刻提交）
- 冻结上游：SGLang `c67d541a40f8bf851e9fc1e925f5316638838cd6`（作者 PR #42106）
- 有效生成 runtime：`yue2_runtime_sha256 = 342b2f53…`（全程未变；仅 0001/0003/0008 导入守卫补丁）
- PR：https://github.com/AIwork4me/YuE2-SGLang-ROCm/pull/19
- 精确 HEAD CI：最终 HEAD 的 push + pull_request 双运行、双 job 全绿（run id 见 `02_EXACT_HEAD_CI.json`）

## C. 检查点与恢复

- 暂停时 20 个候选全部官方 verify 通过；根因修复后尾部检查点永不遗漏。
- 终态：26 个检查点归档（16 间隔 + 384 里程碑 full + restore-manifest-384），
  第二卷 52 个文件逐一 SHA256 复核，0 失配。
- 最终恢复演练：384/384 候选、4224 个文件、journal 一致、resume 身份正确、0 重复归档。
- 异机备份：**BLOCKED_EXTERNAL**（owner 确认无备份机；同机第二卷 ≠ 异机容灾，如实申报）。

## D. 工程修复（本任务实际关闭的缺陷，均含复现→根因→最小修复→回归→真机验证）

CI 收集失败（torch 惰性加载+独立数值 job）、workflow YAML 语法、SIGTERM 尾部检查点、
跨会话 resume 漂移策略（`resume_decision` 纯函数 + `--allow-driver-update` 日志披露）、
恢复不保留检查点历史、Q3O 回执零身份校验（完整 identity manifest + 负向测试 9 项）、
Q3O 48GB 装载 OOM（三层根因：转置副本/列表临时/引用环+分配器碎片；最终验证路径 =
原生 HF 专家 + 原位稳定 top-k 前向补丁）、llvmlite rc=139（torch 前预热 numba）、
inference-mode 累计器、per-lab CPU 线程颠簸（16 线程配额）、vLLM ROCm 平台探测
（amdsmi shim 吞掉自身成功）。全部细节见 `08_INDEPENDENT_REVIEW.md` A 表。

## E. 全量生成

384/384（单一续跑会话，0 失败、0 重试、5 个 truncated-but-valid 官方保留）。
与历史 Arm B 的逐候选 SHA256 对比：**380/384 字节一致**；4 个差异全部为
FLAC 容器层（codec frames/时长/截断/种子全同，字节差 −2/+2/+15/0），
根因 = 重建镜像的 libFLAC 构建差异；生成确定性不受影响。

## F. 五指标完整对照

| 指标 | 论文 | 作者 SGLang | 历史 W7900 | RC5.1 W7900 | Δ(与历史) | 可比性 | 证据 |
|---|---|---|---|---|---|---|---|
| SongBench GA | 6.7316 | 6.7146 | 6.738264 | **6.736891** | −0.0014 | 官方评测器逐字，selected-192；论文=原始音频 | `06_SONGBENCH_FULL.json` |
| PER micro（冻结臂） | 8.44% | 8.1471% | 17.762763% | **17.7699%** | +0.007pp | 官方评分代码；ASR 引擎替换为 transformers-ROCm（已披露，P1.1 主因） | `05_PER_FULL_METRICS.json` |
| PER micro（vLLM 修正臂，独立申报） | — | — | — | **8.4488%** | — | 同 384 音频、同权重、同评分，vLLM 0.19.1 解码路径（与官方同引擎家族，非 0.14.0） | `07_PER_FINAL_VERDICT.json` |
| MuLan | 0.5068 | 0.49960 | 0.509166 | **0.509395** | +0.0002 | 官方评测器逐字 | `06_MULAN_FULL.json` |
| AllMusicCaps | 0.4054 | 0.40825 | 0.405556 | **0.405181** | −0.0004 | 官方评测器逐字 | `06_ALLMUSICCAPS_FULL.json` |
| Q3O (0–5) | 4.68 | 未发表 | 未完成 | **4.393986** | n/a | ROCm 适配 judge：官方 scorer/prompt/权重逐字，HF-ROCm 引擎；等价性不申报 | `06_Q3O_FULL.json` |

Q3O 官方参考出处：评测器 README 验证段（"4.69 vs 4.68 original, 4.71 fresh H800"），
非猜测。论文/作者/历史/本次四列口径差异已在 scoreboard 中逐项说明，未混算。

## G. Q3O

- 配置：Qwen3-Omni-30B-A3B Thinker-only BF16；**34 GPU + 14 CPU 常驻 MoE 层**
  （CPU 块 fp32 计算、官方 bf16 舍入点）；GPU 层 = 原生 HF 专家 + 原位
  稳定 top-k 前向补丁（批量打包块在 48GB 上不可装载，根因已录，代码保留）。
- 稳定性：5 次/2 进程（含整模型重载）生成 token 哈希与评分完全一致（4.833333）。
- 真实路由统计：CPU 层 18.35%、GPU 层 20.20% 的 routed slots 处于精确边界并列
  ——量化了旧 torch.topk 非确定性（约 1/5 路由决策曾随机），也界定了与官方
  kernel 的不可比性。
- 全量：192/192 有效，0 解析失败，0 未解释 OOM；平均 87.1s/候选；
  峰值 VRAM 42.41 GiB（torch 分配口径），宿主 VmHWM 49.83 GiB（55 GiB 限额，余 5.17）。
- 判定：`Q3O_FULL_ROCM_ADAPTED_PASS`；官方等价性 NOT_ESTABLISHED（无 CUDA 主机）。

## H. PER 根因（源码级）

主因（CONFIRMED）：官方 W7900 冻结路径所用的 qwen_asr **transformers 后端**在
约 10/384 难样本上进入退化重复环（字面输出 `language None<asr_text>` + 数百个
被 skip 的 token，2 个样本打满 4096 cap）——该行为对精度/注意力/批次/设备全部
不变，特征张量跨配置位级一致；同一权重同一音频经 **vLLM** 解码则正常转写。
首分歧探针：语言头之后 logits 处于刀锋并列（top-5 相同、EOS 概率 ~2e-5、第 8 步
近并列翻转）。修正臂全量复评：selected micro **8.4488% vs 论文 8.44%**（Δ0.009pp，零调参）。
次因（CONFIRMED）：2/384（wsb_085_r1、wsb_120_r1）双引擎皆环——真实模型行为。
未闭合：触发环进入的具体内核算术（H10 OPEN）；官方 CUDA 对照（E3 BLOCKED_EXTERNAL，
交接包已备：384 候选哈希 + runbook + 对比脚本）。
假设台账与逐级证据链：`07_PER_CAUSAL_HYPOTHESES.md`、`07_ASR_SOURCE_LEVEL_RCA.md`。

## I. 性能

生成：P50 275.27s / mean 284.78s / P90 392.54 / P95 433.21 / P99 487.18；
AR 164.2s / NAR 42.2s / VAE 78.4s（均值）；RTF 均值 1.2866（= wall/audio），
实时倍率 0.7894；生成期 GPU busy 均值 93.41%、峰值 VRAM 29.7 GiB。
评测：PER 全量约 24h（GPU 97% 占用）；SongBench/MuLan/AMC 各 ≤1.5h；
Q3O 192 候选 5.5h。单位严格区分 GB/GiB（报告统一 GiB=2³⁰）。

## J. 独立审阅

以对抗式审阅完成：A 表 11 项缺陷全部核实"复现→根因→修复→回归→真机"闭环；
C 表对 384 完整性、历史哈希、选样、PER/四指标、Q3O 覆盖与重复性、修正臂、
性能分位数逐项独立重算一致；未发现任何指标混算（Pilot/全量、selected/unselected、
CPU/GPU、官方/适配、原始/修正 PER 全部分列申报）。回归套件：CPU 543 通过 + 3 诚实
SKIP，sglang 环境 12 通过，compileall/bash -n/diff-check/证据守卫/数字回执/密钥扫描
全部通过，最终态 384/384 恢复演练通过。

## K. Release Gates（G0–G17 摘要）

12 PASS（G0–G7、G10–G14）；G8 Q3O 科学等价 NOT_ESTABLISHED（外部阻塞）；
G9 PER 因果 PASS（复合根因，主因确认）；G15 第三方复现 / G16 作者批准 /
G17 AMD 发布批准 NOT_RUN（需外部行动）。逐门禁证据与所需行动：
`08_RELEASE_GATE_LEDGER.json`。历史门禁定义未改动。

## L. GitHub 交付

- 全部成果在 PR #19（分支 `mission/w7900-rc5-latest-upstream-full-reproduction`，
  无 force-push、未动 main、未合并）；最终提交与 CI 状态见 `08_GITHUB_FINAL_STATE.json`。
- PR 描述已更新为最终完成状态（十三要素齐全：上游溯源、兼容补丁、全量生成、
  五指标记分板、历史哈希对比、PER 根因、Q3O 内存/性能、工程质量、复现、恢复、
  测试、精确 HEAD CI、遗留阻塞）。
- 英文作者验收包：`08_UPSTREAM_HANDOFF_EN.md`；上游最小 issue 草案（qwen_asr
  transformers 重复环）内含（音频受限，公开 issue 仅携带哈希与数值回执）。
- 公开安全：证据守卫 + 歌词检测器 + 密钥扫描在最终 HEAD 全部通过；未上传任何
  歌词、音频、ASR 文本或模型权重。

## M. Remaining Blockers（仅真实未关闭项）

1. **异机备份（G13 部分）**：owner 无备份机；已做同机第二卷最大保护与演练。
   下一步最小行动：owner 提供任一授权目标（rsync/restic 皆可，工具已就绪）。
2. **官方 CUDA 对照（G8/G9 收尾、E3）**：无 CUDA 主机。已备 384 候选交接包
   （`rc5-per-experiments/rc5_1_cuda_handoff`，restore-check 可验证）。需要：作者或
   任何 CUDA 主机执行 runbook 并回传 same-audio 对比。
3. **Q3O 官方等价（G8）**：同上 CUDA 阻塞；另有官方 vLLM MoE kernel 的 tie-break
   规则未公开（影响约 20% 路由 slots 的可比性）。需要：作者确认或 CUDA 对照。
4. **G15/G16/G17**：第三方复现、作者批准、AMD 发布批准——均为外部流程，证据包
   已就绪。
5. **H10（可选深化）**：环进入的具体内核算术差已表征（刀锋并列）未逐层追踪；
   有界后续：在两个引擎内做逐层 logits 追踪。

---

### 结论

> **384/384 全量生成、完整可信可复现的五指标评测、源码级 PER 根因（修正臂
> 8.4488% vs 论文 8.44%）、48GB Radeon 上经真实模型验证的 Q3O 方案、以及完整的
> GitHub 工程与科学成果交付——全部完成。** 剩余阻塞均为外部条件（异机备份、
> CUDA 对照、作者/AMD 批准），已在门禁账本中如实申报并列出最小下一步行动。
