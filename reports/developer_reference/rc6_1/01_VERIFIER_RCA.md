# M1 — Developer Verifier RCA (V01–V10)

工具：`scripts/rc6_verify_results.py`（RC6.1 重写，schema `yue2-rc6_1-developer-verification/2`）
基线：RC6 版本（commit `eeb2115`）。
证据：`01_VERIFIER_NEGATIVE_CONTROLS.json`（22 项控制，17 项在 RC6 版本上现场复现缺陷，RC6.1 全部 fail-closed）+ `tests/test_rc61_verifier.py`（25 测试，修复前 15 failed / 1 passed，修复后 25 passed）。

## 逐项根因与修复

| # | RC6 缺陷（现场复现） | 源码级根因 | 修复 | RED→GREEN |
|---|---|---|---|---|
| V01 | 单首歌无 GPU lifecycle receipt 仍得 `VERIFIED_REFERENCE_RUN` | `classify()` 单歌路径只看 `generation_config.matches_reference` 与 `model_identity.matches_pinned`，与 GPU 证据完全无关 | 新增 `gpu_execution` 层：定位 lifecycle receipt（`--gpu-receipt` / run-dir / ../logs），验证 receipt_type、`gpu_identity` 步骤 `GPU_EXECUTION_VERIFIED`、BDF、spawn pid+starttime、`cleanup_state==CLEAN`、cmd 绑定本 run 的 request.json；缺失→`INCOMPLETE`，无效→`FAILED` | NC01/NC02 ✅ |
| V02 | 音频内容未绑定生成收据 | `verify_single_song()` 只读 result.json 声明字段，从不重算 artifacts 哈希 | 逐个 artifact 重算 sha256 与声明比对；不一致→`FAILED` | NC07 ✅ |
| V03 | WAV 与 FLAC 内容不对应仍通过 | 两文件各自独立检查，无交叉验证 | `pcm_equal()`：native 整数域比较（libsndfile FLAC 左对齐 int32 归一化后按粗精度对齐），WAV PCM_16 ↔ FLAC PCM_24 repack 逐样本相等 | NC08 ✅ |
| V04 | journal 384 行 complete 即可授予完整验收 | `verify_campaign()` 只统计 journal 行数 + 前 8 个音频抽样 | 每个 complete 行审计：bundle 存在、artifact 哈希重算、result.json status、journal seed ↔ request.json seed、ID 形状（每 prompt 恰好 r0/r1）；另委托官方 `verify_wsb_artifacts.py`（manifest 种子保真 + 伪造 bundle 重算） | NC10/NC11/NC12 ✅ |
| V05 | 仅抽查前 8 个音频 | `complete[:8]` 采样 | 默认全量审计；`--quick` → `SAMPLED_INTEGRITY_CHECK`，永不授予完整判定 | NC09/NC19 ✅ |
| V06 | GPU identity 缺失仅记 caveat | caveat 不影响 `classify()` | campaign 无 lifecycle 会话→`gpu_execution=NOT_VERIFIED`，判定封顶 `INCOMPLETE`；receipt 无效→`FAILED` | NC03/NC16 ✅ |
| V07 | `runtime_sha256=None` 被当作匹配 | `runtime.get(...) in (REFERENCE[...], None)` 把 None 列入合法值 | 严格 `==` 比较，None → `MISSING` → `FAILED` | NC05/NC17 ✅ |
| V08 | 未验证五指标覆盖仍可 `VERIFIED_REFERENCE_RUN` | campaign 判定与评测完全无关 | `evaluation_coverage` 层（run-dir summaries + `--eval-receipts` 适配 rc5_1 报告格式）；缺指标→封顶 `VERIFIED_FULL_GENERATION`；五指标齐→`VERIFIED_FULL_BENCHMARK`/`VERIFIED_REFERENCE_RUN` | NC22 ✅ |
| V09 | 任意数量 complete 可当 pilot | `VALID_PILOT_ONLY` 只要求 `complete>0` | 官方 pilot 协议固化：恰好 10 候选、prompt 集 {0,1,2,79,81}、每 prompt {r0,r1}；否则 `INCOMPLETE` | NC18 ✅ |
| V10 | compare 只输出参考文件路径与说明 | `--compare-reference` 分支只写两个字符串 | 真实比较：读取用户记分板（`<run>/scoring/summary.json` 或 `--eval-receipts`）与冻结参考记分板，逐指标输出 reference/observed/absolute delta/relative delta/coverage/eligibility；无用户数据→显式 `NOT_PERFORMED` + reason | NC + 单测 V10/V10b ✅ |

## 附加封闭的路径（M1.7 负向控制）

- GPU receipt 来自另一 run（cmd 引用不同 request.json）→ FAILED
- 错误 BDF（`--expect-bdf`）→ FAILED
- 错误 model SHA / runtime SHA → FAILED
- 损坏的 journal 行（中间/末尾）→ FAILED（不再静默跳过）
- 383/382 行的截断 run → INCOMPLETE（不得呈现为 FULL）
- 伪造 384 ID 形状 → FAILED
- 重复 candidate id → FAILED
- journal 行无对应 bundle → FAILED

## 诚实披露（不声称的能力）

- 单首歌“完全自洽的伪造”（音频+收据+request 全部替换为另一首合法歌且元数据重算一致）只能靠参考哈希库或重执行闭环；本工具提供的是 receipt-integrity + identity-chain 验证。此边界写入 `01_VERIFICATION_CONTRACT.md`。
- `--quick` 仅为采样完整性；官方 auditor 不可运行时（无 WildSongBench workspace）`scientific_reference` 封顶 `NOT_ESTABLISHED` 并披露。
- 真实数据回归：first-song（fresh-clone）→ `VERIFIED_FIRST_SONG`；RC5.1 384 campaign（含 5 指标 receipts + 官方 auditor FULL）→ `VERIFIED_REFERENCE_RUN`。
