# 00 — 基线与范围（C1 CPU-Only Engineering Closure）

执行时间：2026-11-15T05:23Z–（进行中）UTC · 执行者：C1 audit session

## 分支与提交基线（执行前实时核实，非转述）

| 项 | 值 |
|---|---|
| 工作目录 | `/workspace/YuE2-CPU-Audit`（独立 clone；运行中的 Arm A 树在 `/workspace/YuE2-SGLang-ROCm`，未被触碰） |
| 工作分支 | `audit/c1-cpu-only-integration`，基于 `78c5cb8`（PR #10 verified HEAD） |
| Parent 链 | `78c5cb8` ← `fix/w7900-cpu-only-risk-closure-20261115`（PR #10，base=`mission/w7900-fresh-image-final-closure`@8c242ba ← `feat/yue2-rocm-publication-readiness`@fdfc0ac） |
| PR 实况（gh 实时） | #7 base `main` head `security/redact-…-20261115` Draft；#8 base `feat/…` head `fix/w7900-armA-…-20261115` Draft；#9 base `feat/…` head `mission/…` Draft；#10 base `mission/…` head `fix/w7900-cpu-only-…-20261115` Draft，CI SUCCESS，MERGEABLE |
| 工作树状态 | clone 后 `git status` 干净（0 未提交）；后续修改全部在本分支提交 |
| 分支保护 | `main` 无保护规则（API 404）；合并受权限约束，本次未获授权不合并 |
| CI 基线 | run 43678955246：113 passed / 26 skipped / 0 failed（PR #10 head） |

## Arm A 安全边界（只读观察，2026-11-15T05:44:48Z）

- 驱动进程 16537 存活（etime 04:04:17），`_gen_worker` 子进程在生成
- journal verified complete = **25/384**，正在生成第 26 个；0 failed
- 磁盘余 1.5T；cgroup ~40/55 GiB（页缓存压力已知，属运行策略范畴，未干预）
- **本 session 未执行任何 GPU 命令、未改运行目录任何文件、未重启/停止任何进程**

## 范围

CPU-only：安全（P1）→ 数值完整性（P1.3）→ journal 可靠性（P2）→ PER 科学
正确性（P3）→ Release Gate/文档（P4）→ CI/回归（P5）→ PR 整合（P6）→
切换方案（P7）→ 报告（P8）。禁止清单见 mission §2，全部遵守。
