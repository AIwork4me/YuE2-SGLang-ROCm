# 04 — Legacy Resume 兼容性（C2 P3.5 实测矩阵）

对象：含历史数据的 run 目录在新驱动下的 resume。原则：**不放宽科学身份，
不因 schema 切换悄悄重生成有效历史音频**（恢复以 verify_result 为准，
与 C1 语义一致）。

| # | 场景 | 行为 | 测试 |
|---|---|---|---|
| 1 | 旧 run_config（无 driver_protocol/有 information 域） | stable 比较（VOLATILE+informational_note 排除）通过→resume；缺 driver_protocol 由 C1 迁移先例处理（owner 日志化） | test_resume_ignores_volatile_timestamp_fields（C1，仍绿） |
| 2 | 旧 journal（无 attempt_id 记录） | 正常计数/跳过；溯源=LEGACY_PROVENANCE_INCOMPLETE | verifier legacy 测试 |
| 3 | 旧 `_gen_worker.py` 存在且=当前 GEN_WORKER | 快照复用；旧文件不动 | snapshot 复用测试 |
| 4 | 旧 `_gen_worker.py` 存在但≠当前 | 旧文件原样保留+另存快照；执行走新快照；journal 新记录带新 sha——同 run 内双版本**可区分** | legacy-preserves 测试 |
| 5 | 旧 `_gen_worker.py` 不存在（全新 run） | 快照+惯例文件双写（均 write-once） | fresh-run 测试 |
| 6 | 同 Stable Identity / 不同 Worker Source | resume 允许（协议未变）；每次 attempt 记录各自 worker sha | snapshot-new-content 测试 |
| 7 | 同 Worker Source / 不同 Stable Identity | run_config 比较拒绝（exit 3）——不变 | C1 identity 测试（仍绿） |
| 8 | 产物完整但 journal 未写成功 | `resume_verified_candidate` 以官方 verify_result 收回为 complete（recovered 记录，C1 语义） | C1 恢复测试（仍绿） |
| 9 | 失败后重试 | 新 attempt_id 新收据；journal failed→complete 最新胜出 | C1 fault-injection #5 |
| 10 | 重复启动 | gpu_lock flock 串行（等待/超时退出） | C1 lock 测试（仍绿） |
| 11 | 并发启动 | 同上；journal flock 原子追加 | C1 并发写测试（80/80） |
| 12 | 部分证据损坏 | 快照损坏→tampered 拒绝；收据缺失→violation 报告；**均不触发重生成已验证音频** | snapshot-tampered / crash-window 测试 |

**结论**：历史 Run 安全；缺失逐候选证据处标记 UNKNOWN/LEGACY，不推断；
无任何"迁移"性写操作作用于旧收据（新增全部是新增文件，旧文件只读）。
