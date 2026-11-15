# C2 CPU-Only Scientific & Provenance Hardening — 中文最终报告

执行：2026-11-15T07:22–07:45 UTC · 分支 `mission/c2-scientific-provenance-hardening`
（基于 PR #10 head `8756125`） · 集成 dry-run 树全绿（197/26/0）

---

## 1. 修复了哪些真实 Bug？

1. **PER→"空转写"误分类**（`build_per_reference_package.py`：`per>=0.999`→
   `empty_transcript`）。
2. **官方 Selection 过度声明**（`per_tail_analysis.py`：字段缺失仍标
   VERIFIED）。
3. **音频身份链断裂**（打包只哈希输出文件；flac 被换仍"合法"）。
4. **Worker 源码可被静默覆盖**（无条件 `write_text`；历史候选代码不可证）。
5. **逐候选生成代码零溯源**（仅 run 级单一 sha）。

## 2. 原始代码为何错误？

见 01/02/03/05 号文档"缺陷"节——共同模式：**以推断替代证据**（PER 推断空、
字段缺失推断通过、文件名推断身份、最新源码推断历史）。

## 3. 如何重现？

每个缺陷在对应测试的 Before 分支可复现（如：删 summary 的 audio_sha256 字段
→旧代码仍 VERIFIED；两次不同 GEN_WORKER→旧 `_gen_worker.py` 被覆盖；换 flac
字节→旧打包照常出"合法"manifest）。

## 4. 改了哪些代码？

新增：`scripts/sample_classification.py`、`scripts/verify_provenance.py`。
重写/加固：`scripts/build_per_reference_package.py`（五链身份+fail-closed）、
`scripts/per_tail_analysis.py`（分层验证+守恒+标签交叉表）、
`scripts/run_wsb_torch.py`（快照/session/attempt 收据接入，生成协议零改动）。
测试：新增 43 个 C2 专用 + 升级 4 个既有（61 项变更见 07 文档）。

## 5. 每个修复的正/负测试？

01/02/03/05 文档逐项列表（负向对照含：伪造 sha、篡改快照、穿越、symlink、
覆盖、崩溃窗口、PER=1 三态、缺权利标志……全部真实文件操作）。

## 6. Benchmark Semantic Change？

**无**（08 文档）：锁文件零改动；数值收据零漂移（1851 叶子 CI 级验证）；
选择规则只收紧（发表级现在要求更高，不放宽）；历史四指标不动。

## 7. Provenance Schema 如何兼容历史 Run？

04 文档 12 场景矩阵：legacy 记录=LEGACY_PROVENANCE_INCOMPLETE（可归因仅当
旧 `_gen_worker.py` 哈希==run_config 记录）；旧文件永不改写；同 run 双 worker
版本可区分；崩溃/伪造=violation。

## 8. 音频 Hash 如何证明真实音频？

五链（02 文档）：官方 selection 的 audio_sha256(=评分 MP3) ↔ encoding 收据
↔ 现存 mp3 字节 ↔ source_flac_sha256 ↔ flac 现存字节 ↔ 拷贝字节+只读导出。
任何一环缺失/失配→整包拒绝。

## 9. 官方 Selection 验证了哪些字段？

四字段契约（wsb_eval.py:355 实读）：prompt_index/candidate_index 恒验；
seed/audio_sha256 逐项计数（192/192 才是 AUDIO_IDENTITY_VERIFIED；
缺失→COORDINATES/INCOMPLETE 层，missing_fields 列明）。

## 10. 哪些身份字段仍 UNKNOWN？

公开数值收据上的**全部 ASR 转写文本**（EMPTY_UNKNOWN——需受限原件核对
transcript_sha256）；legacy 候选的逐候选代码版本（LEGACY_*）； Arm A 进行中
候选的评分侧身份（打分未开始）。

## 11. CPU 测试 PASS/FAIL/SKIP？

**197 passed / 0 failed / 26 skipped**（skip=官方 manifest 类，逐项分类于
07 文档；本机带 manifest 时全绿）。

## 12. GitHub CI Run URL？

见 PR 描述与下方"最终核验"（精确 HEAD 的 CI 在 push 后回填于 PR）。

## 13. 是否影响正在运行的 Arm A？

否。零 GPU 命令；零运行目录（`/workspace/YuE2-SGLang-ROCm`、
`/data/yue2-runs/armA_wsb_full`）修改；零进程干预。只读状态证据：
07:40:33Z **35/384**，driver ALIVE。

## 14. 哪些问题仍必须等待 W7900？

G3 close() 显存 · G10 AR Hang/HIP fault 根因 · Arm A 384 完成+审计+四指标 ·
Arm B 复现 · 真实数据上的 P2 五链与 P4 分层验证（评分后） · G20 溯源物理验证。

## 15. C2 是否可以宣布完成？

**A. C2 CPU-only Engineering Verdict：GO**（成功标准逐条达成：分类有证据/
身份可溯/选择语义收紧/守恒/四指标不变/身份链 fail-closed/权利门禁/快照不可
静默改/attempt 可追溯/legacy=UNKNOWN/集成 dry-run 无敏感回流/CI 绿/Arm A
无扰）。

## 16. 是否可以冻结 CPU-only 工程？

**是**——A-verdict GO 且 12 号 mission 条款满足（G3/G10/G15 维持 BLOCKED，
无未申报的 CPU 遗留缺陷；后续全部为 GPU/数据/Owner 依赖项）。建议冻结点=
本 PR 合并之时。

## 17. 下一步为什么应该转向物理验证？

CPU 侧的可修复面已穷尽：剩余每一项 BLOCKED/NOT_TESTED 都需要 W7900 或真实
评分数据（close()/Hang/HIP 根因=物理复现；PER 因果=真实 ASR 对照；发表=
campaign 完成+官方打分）。继续 CPU 工作只会增加测试数量而非关闭缺陷——
违背 mission 原则 9。

---

## B. Full YuE2 ROCm Benchmark Publication Verdict：**NO-GO**

Arm A 35/384 进行中；Arm B 未启动；官方四指标未产；PER 17.77 vs 8.44 因果
未闭合；G3/G10/G15 BLOCKED；独立科研复核未发生。A 的 GO 不替代 B——发表
GO 需上述全部关闭后由 Owner+独立评审作出。
