# 03 — CI 与变异控制结果（W7900-RC3）

## 1. 本机套件（推送前基线）

- 精确 CI 范围（`.github/workflows/ci.yml` 排除 3 个硬件文件）：
  **388 passed / 0 failed**（373 RC2 基线 + 15 RC3 新增）。
- guards：public_evidence_guard / evidence_lyrics_detector（tier1+tier2,
  1813 真实歌词窗）/ verify_numeric_receipt_integrity（1883 叶 0 差）/
  compileall / bash -n —— 全部 PASS。
- 硬件条件测试（sglang venv / 历史 GPU 音频产物 / opt-in live server）：
  本环境 NOT_TESTED-SKIPPED 如实标注（非 CI 范围）；其中 live-server 行为与
  生成/恢复路径已由 P3–P8 真实 GPU 回归覆盖（见 03_PHYSICAL_REGRESSION）。

## 2. 变异控制（本次新修复，全部真实执行）

| 变异 | 靶向测试 | 结果 |
|---|---|---|
| M1 is_truncated 回退 truthiness | test_truncation_counting.py | **KILLED**（1 failed） |
| M2 移除 verifier symlink 拒收 | test_symlink_escape_rejected | **KILLED** |
| M3 id 契约弱化为 `.+` | test_path_traversal_manifest_id_rejected | **KILLED** |
| M4 去掉 inputs path 白名单 | test_absolute/traversing_inputs_path_rejected | **KILLED** |

RC2 既有 5+16 变异控制记录不复跑（套件已把杀灭钉进常规断言）。

## 3. 远端 CI（推送后以实际 SHA 为准）

- 推送前 PR #16 head f6b24d7：cpu-tests 2×SUCCESS（runs 44462151645, 44462144306）。
- 本次新增提交后的精确 HEAD CI 结果见 04_GITHUB_HANDOFF.md 的实况记录
  （本文件不预填未发生的 CI 结论）。
