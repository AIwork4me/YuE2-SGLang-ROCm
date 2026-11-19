# 09 — Release Gate 台账（C2 后）

依据：fresh_image/FINAL_RELEASE_GATE_LEDGER.json + C2 实测。状态词表严格
PASS/FAIL/BLOCKED/NOT_TESTED。

| Gate | C2 前 | C2 后 | C2 依据 |
|---|---|---|---|
| G0 环境 | PASS | PASS | 复核 |
| G1 三环境收据 | PASS | PASS | C1 补全的 uv freeze（8756125 已修正文档叙述） |
| G2 pins | PASS | PASS | 复核 |
| G3 API 验收 | BLOCKED | **BLOCKED（维持）** | close() 显存问题需物理调查/Owner waiver——C2 无 GPU，不解锁 |
| G4-G9,G11-G14,G16,G17,G19 | NOT_TESTED | NOT_TESTED | 依赖 Arm A/B/GPU/Owner |
| G10 缺陷修复 | BLOCKED | **BLOCKED（维持）** | CPU 工具链再进一步（P1-P4 关闭）但 AR Hang/HIP fault 根因仍开放——按 mission 12 保持 |
| G15 安全许可 | BLOCKED | **BLOCKED（维持）** | 工作树已清（PR#7 merged）；历史对象+权利仍待 Owner |
| G18 上游归属 | PASS | PASS | 08 文档（C1）+ C2 无新上游面 |
| **新增 G20（建议）** | — | NOT_TESTED | 逐候选溯源链在真实 Arm A Run 上的物理验证（需 campaign 完成+新驱动切换，见 10 号文档） |

**禁止 Publication GO 的条件未变**：G3/G10/G15 BLOCKED + 新镜像 Benchmark 未完成。
C2 的 A-verdict（工程）不替代 B-verdict（发表）——见 FINAL_REPORT 第 14 节。
