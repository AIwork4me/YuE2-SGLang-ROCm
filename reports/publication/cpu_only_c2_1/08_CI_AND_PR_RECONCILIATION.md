# 08 — CI 与 PR 对账（C2.1）

## 本地（Exact HEAD 见最终提交）
`compileall`/`bash -n` OK · **243 passed / 0 failed / 26 skipped**（较 C2 的
197 → +46：C2.1 新测试 44 + M3 缺口测试 1 + 原有升级；skip=官方 manifest
类，逐项分类见 C2 07 文档，未变）· guard/detector/integrity 全 PASS ·
变异控制 5/5 KILLED。

## GitHub（最终 HEAD 的 CI）
精确 HEAD 与 run URL 在推送后回填于 PR 描述与本节尾行：
CI-RUN-PLACEHOLDER

本地 243/26 与 GitHub 统计可能差 ±2（runner 无 /tmp 权限语义差异等环境类
skip），以 GitHub 精确 HEAD run 为准；两者 0 failed 一致性为验收条件。

## PR 布局
stacked Draft PR（base=`mission/c2-scientific-provenance-hardening`=PR #11
分支）；不自动合并；PR #8/#9/#10 不受影响。
