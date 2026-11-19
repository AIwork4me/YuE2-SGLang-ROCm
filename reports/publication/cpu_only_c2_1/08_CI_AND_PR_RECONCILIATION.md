# 08 — CI 与 PR 对账（C2.1）

## 本地（Exact HEAD 见最终提交）
`compileall`/`bash -n` OK · **243 passed / 0 failed / 26 skipped**（较 C2 的
197 → +46：C2.1 新测试 44 + M3 缺口测试 1 + 原有升级；skip=官方 manifest
类，逐项分类见 C2 07 文档，未变）· guard/detector/integrity 全 PASS ·
变异控制 5/5 KILLED。

## GitHub（最终 HEAD 的 CI）
精确 HEAD 与 run URL 在推送后回填于 PR 描述与本节尾行：
- 精确 HEAD `670d97b`：push run https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/43715755044 (success, 57s) · PR-event run https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/43715761224 (success, 1m2s)
- 本文档回填所在的 docs-only 提交：其自身 CI run 即该提交HEAD 的最终证据（本节下次维护时追加）

本地 243/26 与 GitHub 统计可能差 ±2（runner 无 /tmp 权限语义差异等环境类
skip），以 GitHub 精确 HEAD run 为准；两者 0 failed 一致性为验收条件。

## PR 布局
stacked Draft PR（base=`mission/c2-scientific-provenance-hardening`=PR #11
分支）；不自动合并；PR #8/#9/#10 不受影响。

## 2026-11-16 — Final Freeze Patch Tracking

代码变更：`scripts/verify_provenance.py`、`scripts/build_per_reference_package.py`。新增 `tests/test_c2_1_final_freeze.py`（8 个 CPU synthetic-case 测试）；其余 Benchmark、Model、VAE、Scorer、Protocol Lock 和评分数据均未修改。

- PR #12 原始 HEAD `d66ffbfd` 的 CI `241 passed, 28 skipped` 属于**修复前**运行，不可作为本次补丁的验收证据。
- 需检查 PR #12 **最终 exact HEAD** 的 push 和 pull_request 工作流均 SUCCESS，并逐项核对新 8 项是否真正被执行；报告 CI skipped 不得冒充通过。
- 实验环境差异：本地历史 `243 passed/26 skipped` 与修复前 GitHub `241 passed/28 skipped` 不可以混写；GitHub 有 2 项额外 Tarball 依赖跳过。
- 真实 WildSongBench Tier 2、G3/G10/G15/G20 与 Arm A/B 新镜像仍不属于本次 GPU-free CI 的通过范围。
