# M1 — Developer Verification Contract (RC6.1)

适用工具：`scripts/rc6_verify_results.py`（schema `yue2-rc6_1-developer-verification/2`）。
本合同是公开承诺：每个判定词的含义、所需证据、以及明确不声称的能力。

## 1. 验证层级（低层绝不自动推导高层）

| 层 | 含义 | 证据来源 |
|---|---|---|
| `audio_integrity` | WAV/FLAC 可解码、48 kHz 立体声、非静音、有限值、WAV↔FLAC PCM 逐样本一致、artifact 哈希重算一致 | 实际文件字节 |
| `gpu_execution` | GPU lifecycle receipt 绑定本 run：`gpu_identity` 步骤 `GPU_EXECUTION_VERIFIED` + BDF（可选 `--expect-bdf` 严格匹配）+ spawn pid/starttime + `cleanup_state==CLEAN` + cmd 引用本 run 的 request.json | lifecycle-receipt.json |
| `model_provenance` | result.json 声明的 MoT/VAE 哈希 == 冻结 pins；`--model-root` 提供时另对模型文件重算（`recomputed_from_disk`） | result.json + 可选磁盘重算 |
| `runtime_provenance` | `runtime_sha256` 严格等于冻结值（None 不匹配） | config.json / run_config.json |
| `generation_protocol` | cot/cfg/vae/ode/max_tokens 等与参考协议一致（差异→disclosed） | config.json |
| `generation_coverage` | FIRST_SONG / OFFICIAL_PILOT(5×2, indices 0,1,2,79,81) / FULL_384；每行 bundle 审计 + 官方 auditor 委托 | journal + songs/ + verify_wsb_artifacts |
| `evaluation_coverage` | 五指标 receipts 覆盖同一选样（run-dir summaries / `--eval-receipts`） | 评分收据 |
| `scientific_reference` | FULL_384 + 五指标 + 官方 auditor FULL（manifest 种子保真、伪造 bundle 重算） | 全链 |

## 2. 判定词与必要条件

| 判定词 | 必要条件（全部） |
|---|---|
| `VERIFIED_FIRST_SONG` | 单歌；audio+model+runtime+gpu 四层 VERIFIED；协议一致 |
| `VERIFIED_WITH_DISCLOSED_DIFFERENCES` | 单歌身份链完整，仅协议/配置差异（disclosed_differences 列出） |
| `VERIFIED_BENCHMARK_PILOT` | 官方 pilot 形状 10/10 + GPU 层 + 五指标 pilot 评分 |
| `VALID_PILOT_ONLY` | 官方 pilot 形状 10/10 + GPU 层（无评分；legacy 名称保留） |
| `VERIFIED_FULL_GENERATION` | 384/384 全 bundle 审计 + 身份链（无评分声明） |
| `VERIFIED_FULL_BENCHMARK` | + 五指标覆盖（同选样） |
| `VERIFIED_REFERENCE_RUN` | + 官方 auditor FULL + scientific_reference VERIFIED |
| `SAMPLED_INTEGRITY_CHECK` | 仅 `--quick`；采样审计通过；永不授予完整判定 |
| `INCOMPLETE` | 证据链缺失（如无 GPU receipt / 覆盖不足）而无硬失败 |
| `FAILED` | 任一硬检查失败（哈希不绑、PCM 不符、伪造形状、损坏 journal…） |
| `UNSUPPORTED_CONFIGURATION` | GPU arch 在验证矩阵外（保留 RC6 行为） |

退出码：0 = 任何 VERIFIED*/VALID_PILOT_ONLY/SAMPLED tier；1 = FAILED/INCOMPLETE；2 = 用法致命。

## 3. 兼容性

- 旧判定词 `VERIFIED_REFERENCE_RUN`/`VALID_PILOT_ONLY`/`VERIFIED_WITH_DISCLOSED_DIFFERENCES`/`UNSUPPORTED_CONFIGURATION`/`INCOMPLETE`/`FAILED` 保留，但语义收严（单歌不再可能 `VERIFIED_REFERENCE_RUN`——这是 RC6 误授予路径的修复本身）。
- 输出新增 `verification_scope`、`disclosed_differences`、`sampled_only` 字段；schema 升至 `/2`。
- CLI 新参数：`--quick`、`--gpu-receipt`、`--expect-bdf`、`--eval-receipts`、`--model-root`。

## 4. 明确不声称的能力（诚实边界）

1. **自洽伪造**：若攻击者替换音频并重算 result.json 哈希、同时持有同 request 的 receipt，单歌层面无法仅凭离线收据区分——本工具提供 receipt-integrity 与身份链验证，不声称重执行验证。campaign 层由官方 auditor 的 bundle-identity 重算部分覆盖。
2. **参考分接近≠真实**：`--compare-reference` 输出 delta 与 eligibility 标签；分数接近永远不是验证依据（沿用 RC6 原则）。
3. **Pilot vs Full 不可比**：pilot 观测与 selected-192 全量记分板的 delta 仅为诊断性。
4. **官方 auditor 不可用**（无 WildSongBench workspace）时：`scientific_reference=NOT_ESTABLISHED`，判定封顶 `VERIFIED_FULL_BENCHMARK` 以下，并写入 disclosed_differences。
5. CPU CI 中 numpy/soundfile 依赖的音频检查在真实 GPU 硬件上执行；CI 层面由合成 fixture 单测覆盖（`tests/test_rc61_verifier.py`）。

## 5. 与五指标防混臂的关系

`evaluation_coverage` 只收集同一 run-dir / 同一 `--eval-receipts` 集的指标；跨臂拼接（A 臂 Q3O + B 臂 PER）需要人为构造 receipts，此时 coverage 的 `sources` 字段会暴露来源不一致（不同 run 目录）。Scoreboard 级别的防混臂由 M4 的记分板结构（每臂独立文件）保证。
