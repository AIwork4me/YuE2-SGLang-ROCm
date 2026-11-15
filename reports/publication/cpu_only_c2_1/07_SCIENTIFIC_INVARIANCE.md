# 07 — 科学不变性与安全（C2.1）

Before/After（vs PR #11 base 4d9f4a2，git diff 实测）：

| 项 | 结果 |
|---|---|
| configs/（协议锁/pin） | **0 改动** |
| scripts/per_tail_analysis.py（选择/统计） | **0 改动** |
| 数值收据完整性（verify_numeric_receipt_integrity） | PASS（0 漂移，CI 级） |
| Public evidence guard | PASS |
| Lyrics detector Tier1+合成Tier2 | PASS 292 文件（真实数据集 Tier2 依赖
  本机 manifest，非 CI 声明——状态如实） |
| 修改面 | 仅 build_per_reference_package（P0-A/B）、verify_provenance（P0-C）、
  run_wsb_torch 快照函数（P1-A）、atomic_publish 新模块、测试、本报告目录 |

历史四指标、seeds、模型/VAE/数据集/scorer 零触碰；Arm A 原始证据零触碰。
