# M2 — ASR Evaluator Identity & Durable Resume (RCA)

对象：`scripts/rc6_asr_identity.py`（合同+审计+resume）、`scripts/rc5_asr_vllm_native.py`（runner）、`scripts/rc5_score_transcripts.py`（scorer）。
证据：`tests/test_rc61_asr_identity.py`（15 项，修复前 13 failed / 2 passed → 修复后 35/35 全绿含 RC6 回归套件）、`02_ASR_PHYSICAL_RESUME.json`（真实音频 + 真实 SIGKILL 物理恢复回归）、`02_HISTORICAL_ASR_AUDIT.json`（384 历史回执只读审计）。

## 逐项缺陷 → 根因 → 修复

| # | 缺陷（静态审阅提出，RED 实测确认） | 根因 | 修复 |
|---|---|---|---|
| 1 | audit_receipts 仅比较部分 identity 字段 | 字段子集比较（model files_sha、engine 6 键、decoding 6 键），preproc/scoring/driver 变化不可见 | 字段比较保留（兼容既有 R_* 判定词）+ **完整 identity 绑定**：embedded `run_identity_sha256` 严格相等；无 embedded sha 时对 identity 内容做 canonical 哈希比较 → `REJECT_IDENTITY_MISMATCH`（D1/D3 实测） |
| 2 | 未强制校验完整 run_identity_sha256 | 同上 | 同上 |
| 3 | 未重新计算 transcript_receipt_sha256 | 审计从不重算回执哈希 | 每个回执进入复用逻辑前先重算内容哈希；stale hash → `FAIL_RECEIPT_HASH_MISMATCH`（D2 实测：篡改 repeats 文本被拒） |
| 4 | Missing decoding fields 可能被接受 | 仅比较双方都有的键 | 键缺失 → canonical 内容哈希不等 → REJECT（D3 实测：receipt 缺 temperature 被拒） |
| 5 | Legacy partial identity 可能被标记 reusable | `ri is None` 分支只比 vllm 版本 | vllm 不同 → `REJECT_ENGINE_MISMATCH`（RC6 语义保留）；相同 → `HISTORICAL_RECEIPT_VALID_IDENTITY_PARTIAL`（分析有效，永不 strict-reusable）；`run_identity=None` 的审计同样只给 HISTORICAL_PARTIAL（D4 实测） |
| 6 | 超过 expected repeats 的回执被接受 | 只有 `len(reps) < want` 检查 | `len(reps) > want` → `REJECT_EXTRA_REPEATS`（D5 实测：6/4 被拒） |
| 7 | Incomplete receipt 重跑后追加 duplicate ID | runner 只把 reusable 加入 done，incomplete 行原样留在文件里再追加新行 → 同 id 两行 | `prepare_resume()`：incomplete 行**原子迁移**到 `.superseded-<ts>` 文件（temp+fsync+rename），最终视图每候选恰一条 complete 回执（D9 实测） |
| 8 | 任意位置损坏 JSONL 被当作可修复 tail | 所有 malformed 行都进 `invalid_tail_lines`，`quarantine_tail` 直接丢弃 | 损坏行后有有效行 → `FAIL_MIDFILE_CORRUPTION`（硬错误，resume 拒绝）；仅真末尾撕裂行可修复（D6/D6b 实测） |
| 9 | Quarantine/repair 缺乏原子性 | 直接 `write_text` 覆盖 | `_atomic_write_text()`：temp + fsync + rename + 目录 fsync；quarantine 与 supersede 两处写入都原子（D8 实测：原件保全 + 无 temp 残留） |
| 10 | zip(owner, outputs) 静默截断 | `zip` 语义 | `pair_strict()`：长度不等 raise；runner 的 batch↔wavs 与 owner↔outputs 两处替换（D10 实测） |
| 11 | Manifest duplicate IDs 被字典构造覆盖 | `{r["id"]: r}` | 审计前显式检测 → `FAIL_MANIFEST_DUPLICATE_IDS`（D7 实测）；scorer 同样前置检测（`validate_audio_binding` 之上） |
| 12 | Scorer 仅核对声明 SHA | 只比 transcripts.audio_sha vs manifest.audio_sha | `verify_audio_files()`：文件存在 → 重算真实哈希，不一致 raise；文件缺失 → fail-closed（`--allow-partial` 仅为诊断，summary 记录 `audio_file_verification`）（D11 实测） |

## M2.2 canonical identity schema（新增）

`build_canonical_identity()`：scientific content identity（model files + **processor/tokenizer files** + engine/版本 + preprocessing 源与 **chunking 参数** + **prompt template sha** + decoding（seed/dtype/batch/max_tokens/repeats）+ scoring + driver sha）与 execution provenance（绝对路径、机器信息）分离；哈希只覆盖科学内容——机器迁移不改变科学语义，但执行溯源保留。关键字段缺失 → ValueError（拒绝构建，不允许降级接受）。

## M2.4 物理恢复回归（真实执行）

`scripts/rc61_asr_resume_regression.py`：3 个真实冻结音频候选（只读）；子进程真实 SIGKILL×2（含 mid-line 撕裂写入）；断点验证：torn tail 原子隔离、无数据丢失、无重复 complete id、无 stale identity 复用（identity 改变 → REFUSED）、无篡改回执接受（内容篡改+stale hash → REFUSED）。最终 3/3 REUSABLE。转录文本为合成（engine 标注 MOCK-ENGINE-RESUME-TEST）——本回归测试回执耐久性与 resume 语义，不是 ASR 科学运行（如实声明）。

## M2.3 历史回执处置

384 条 RC5.1 vLLM 臂历史回执（`rc5_1_e2_full/transcripts.jsonl`）只读审计：无 run_identity、无回执哈希（历史格式）→ 384/384 `HISTORICAL_RECEIPT_VALID_IDENTITY_PARTIAL`。冻结的 8.4488% PER 结果**分析有效性保留**；strict resume 不授予。新的严格身份参考运行需在冻结 384 音频上重新执行 ASR（无需重新生成音乐）——本轮未执行（M5 pilot 使用新代码路径评分）。
