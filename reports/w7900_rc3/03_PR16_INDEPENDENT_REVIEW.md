# 03 — PR #16 独立工程审阅（W7900-RC3 第二审）

审阅对象：`mission/joint-blog-rc2`（base `integration/joint-blog-rc` @ 66b5a13）。
方法：全部运行时/溯源/交接文件逐行复读 + 本机精确 CI 范围套件 + 真实 GPU 物理
回归 + 对新修复做变异控制。审阅者区分四个维度给出结论（文末）。

## 1. RC2 已有修复复读（全部接受）

| 修复 | 复读结论 | 物理/GPU 证据 |
|---|---|---|
| resume 精确 `complete`+resumed 标志（run_wsb.py） | 正确；前缀计数向后兼容 | **真实 GPU 验证**：SIGKILL 撕裂态 → 隔离 → 重生成 → 精确 complete + resumed 语义；journal_complete 去重计数 2/2 |
| journal_complete startswith("complete") | 正确（同时吃掉历史 `complete(resumed)` 行） | 同上（重复行不重复计数） |
| score() YUE2_SCORE_TIMEOUT_S=6h 有界 + 超时证据保全 | 正确（stdout/stderr 尾部落盘，锁由上下文管理器释放） | CPU 故障注入测试在套件内 |
| score_stage 有界重试（默认 8 次）+ blocked_reason 升级 | 正确（计数持久化于 mission_state） | 套件内 |
| audit()/acceptance() TimeoutExpired 降级 FAIL | 正确（监督链存活） | 套件内 |
| 同秒 partial 目录碰撞 pid 后缀 | 正确 | — |
| live-server 测试真 opt-in + gpu.lock 在持拒绝 | 正确 | 套件内；本次 CI/GPU 窗口未触碰任何战役 |
| gpu_lock wait 子命令 dest 冲突修复 | 正确（复读 70bef8b） | 本会话 lock acquire/release 行为正常（acceptance 流 + 手动） |
| disk guard 全停（STOP + stopped_by_disk_guard） | 正确 | — |

## 2. RC3 新发现缺陷与修复（本审阅产出）

### D1（P2，安全）：交接 verifier 接受 bundle 外 symlink

- **复现**：把 `songs/<id>/audio.flac` 换成指向 bundle 外同内容文件的 symlink
  （哈希一致）→ 修复前 `rc=0 bundle OK`（真实验证执行，见会话记录）。
- **根因**：仅做 `is_file()`（跟随符号链接）+ 内容哈希比对，无自包含性检查；
  manifest id 亦无命名契约，`../` 穿越可直接构造。
- **修复**（reports/.../verify_transfer_bundle.py）：符号链接一律拒收
  （文件、候选目录、songs/、evaluation_inputs.jsonl 本体）；manifest id 严格
  `wsb_\d{3}_r[01]_s\d{6}` 契约 + 去重 + 索引字段一致性；inputs path 白名单
  `songs/<manifest id>`；文件名拒收 `.`/`..`/带分隔符。
- **测试**：tests/test_transfer_bundle_verifier.py — 1 正向（384 行真实代码路径）
  + 10 负向（symlink 逃逸/悬垂、穿越 id、绝对与相对穿越 path、坏哈希、截断、
  缺必需件、重复 id、索引不一致）。
- **变异控制**：移除 symlink 检查 / 弱化 id 契约 / 去掉 path 白名单 → 3/3 被杀。
- **真实回归**：修复后对真实 Arm B bundle 384/4224 全量通过（正向不破坏）。

### D2（P3，报告准确性）：审计器 truncated 计数 schema 敏感

- **复现**：Arm A result.json 的 `truncated={"abc":false,"semantic":false}`（dict）
  被 truthiness 计为截断 → Arm A audit `truncated_but_complete=384`（真实 ≈0，
  50 抽查 0 截断；Arm B bool 语义正确计 5）。
- **修复**（scripts/verify_wsb_artifacts.py）：`is_truncated()` 帮助函数——
  dict 按任一 stage 真值、标量按 bool。
- **测试**：tests/test_truncation_counting.py（4 语义钉死）+ 变异
  （回退 truthiness → 被杀）。不影响 verdict 逻辑与历史证据（信息字段修正）。

### 观察（不修，记录）

- score() 超时杀直接子进程，评测器若衍生孙进程可能短暂残留——有界重试 +
  blocked_reason 兜底，风险低；列为后续可选加固。
- `/tmp/pytest-of-root/` 下遗留若干历史测试 stub 进程（CPU、无 GPU 占用），
  非本 PR 引入；建议宿主例行清理。

## 3. 全量回归（本机，YUE2_WORKSPACE=/data/yue2）

- CI 精确范围（排除 3 个硬件文件）：**388 passed / 0 failed**（基线 373 + 新 15）。
- 硬件条件测试（非 CI 范围）：test_yue2_rocm_fallbacks（需 sglang venv）、
  test_first_audio（需历史 GPU 音频产物）在本环境 NOT_TESTED 诚实标注；
  test_server_yue2_rocm 为 opt-in（未设 SGLANG_TEST_SERVER，跳过）。
- guards：public_evidence_guard PASS；evidence_lyrics_detector tier1+tier2
  （1813 真实歌词窗）PASS；verify_numeric_receipt_integrity PASS（1883 叶 0 差）；
  compileall + bash -n 全过。

## 4. 维度裁定

| 维度 | 裁定 | 依据 |
|---|---|---|
| CODE_CORRECTNESS | **GO** | 复读零开放 P0/P1；D1/D2 已修并被测试钉死；373+15 全绿 |
| PHYSICAL_VALIDATION | **GO**（本机可执行范围） | smoke、模块导入、完整官方 acceptance 流（真实生成+优雅停机）、SIGINT/SIGKILL 中断-恢复、audit PILOT、lock/端口/VRAM 释放（见 03_PHYSICAL_REGRESSION） |
| SCIENTIFIC_VALIDATION | 工程侧 **GO** / 平价侧 OPEN | 协议不变量零 diff（configs 对 base 无变化）；历史音频/评测器哈希复验未变；选样语义复算一致；PER 平价按 02 系列保持 OPEN |
| RELEASE_READINESS | **CONDITIONAL GO** | 上述全部成立 + CI 绿于精确 HEAD；等待 owner 审阅合入（不自动合并） |
