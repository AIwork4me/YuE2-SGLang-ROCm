# 10 — Arm A 结束后的部署计划（POST_ARM_A_DEPLOYMENT，C2 增补）

以 C1 的 `cpu_only_closure/09_POST_ARM_A_SAFE_SWITCHOVER.md` 四门禁（A 实验
真结束 / B 冻结 / C 新驱动测试 / D 后续任务）为基座。C2 增补：

## Gate C 增补项（新驱动=含 C2 溯源的版本）

C6. **Provenance 冷启动检查**：新驱动 resume Arm A 冻结副本时——
   - legacy `_gen_worker.py`（sha=运行版）被自动快照为 `worker_sources/<sha>.py`；
   - journal 33+ 历史 complete 记录 → `LEGACY_PROVENANCE_INCOMPLETE`（verifier
     报告，exit 0）；
   - 新生成的候选（若有补生成）→ 全带 attempt 收据，`PROVENANCE_VERIFIED`；
   - verifier 在冻结副本上 exit 0 且**仅**报 LEGACY（任何 VIOLATION=切换阻塞）。
   命令：`python scripts/verify_provenance.py --runs <frozen copy>`

C7. **溯源无缝性证明**：同 run 内 legacy 与新记录并存（journal 逐行可辨），
   历史 audio 零重生成（audit FULL 数=384 且 recovered 计数不增）。

## Gate D 增补任务（排在原 D 列表之后）

8. 评分后执行 `build_per_reference_package.py`（需 --rights-confirmed 与
   Owner 权利确认；P2 五链将首次在真实数据上承压）。
9. `per_tail_analysis --selection-summary`（官方 summary.json 就位后）产出
   发表级分析（AUDIO_IDENTITY_VERIFIED 层）。
10. 建议 G20 gate 评定（provenance 物理验证）。

## 不变式

- 本计划仅文档；C2 未执行任何切换/部署（Arm A 仍以 8c242ba 树驱动运行）。
- 任何 Gate 未满足→回到 C1 的阻塞规则。
