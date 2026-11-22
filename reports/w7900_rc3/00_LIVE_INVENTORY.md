# 00_LIVE_INVENTORY — RC3 现场只读审计（2026-11-22T05:00Z 快照）

审计性质：全部只读（除明确标注的验证性重跑）；无战役进程被触碰。

## 1. 主机与运行时

| 项 | 值 |
|---|---|
| hostname | j-7uqnwhrwmv2s44k6zdqzoq5idj |
| OS / kernel | Ubuntu 24.04.4 LTS / 6.8.0-79-generic |
| GPU | AMD Radeon Pro W7900D（gfx1100，device 0x744b，48 GiB） |
| GPU 状态 | idle（0% GPU，27.0°C，11 W，VRAM 0%） |
| ROCm 用户态 | env B torch 2.12.0+rocm7.14.1（sglang 战役栈）；env A torch 2.10.0+rocm7.1（Arm A 战役栈） |
| 磁盘 | / 3.5 T（70% 用）；/workspace NFS 25 G（91% 用） |

## 2. 战役终态（发现时）

- `mission_state.json` stage = **done**（2026-11-20 20:31:36），历史链完整：
  armA_audit → armA_score_per_sb → armA_score_mulan_amc → armB_acceptance →
  armB_campaign → armB_audit（09:38）→ armB_score_per_sb（09:38–20:06）→
  armB_score_mulan_amc（20:06–20:31 rc=0 complete=True）→ done。
- mission_chain.log 末行：`ALL STAGES COMPLETE`。
- GPU lock：`/data/yue2/gpu.lock` 记录最后持有者 `armB-campaign:armB_full_20261119T015756Z`，
  **released_at_utc=2026-11-20T09:34:44Z**（生成结束时自动释放）；无活动持有者。
- 残留进程：仅 2 个 `sglang <defunct>` 僵尸（Nov18/Nov19 起，已由 init 回收等待，不占 GPU）。
- **结论：Arm B 战役已自然终结，GPU 空闲，进入 RC3 收尾窗口。**

## 3. Run 目录

| Run | 路径 | 状态 |
|---|---|---|
| Arm A | /data/yue2-runs/armA_wsb_full（run_id `armA_full_20261115f`） | 384/384，audit FULL（chain 日志） |
| Arm B | /data/yue2-runs/armB_wsb_full（run_id `armB_full_20261119T015756Z`） | 384/384，audit FULL，四指标打分完成 |

## 4. Arm B 关键事实（本次独立重验，非转录）

- `generation_summary.json`：expected 384 / complete 384 / resumed 0 / failed 0 /
  pending 0；wall 113 775 s（≈31.6 h，≈296 s/候选）；peak VRAM 51.5 GB（含 GTT 3.1 GB）；
  finished 2026-11-20T09:34:43Z；stopped_by_signal=false。
- `audit.json`：verdict **FULL**，verified_complete 384，missing 0，
  truncated_but_complete 5，unique prompts 192，identity_reverified 384，problems 0。
  本次用官方 verifier 独立重跑（先备份），输出与 chain 产物**逐字节一致**。
- `run_config.json`：torch 2.12.0+rocm7.14.1；sglang ced0ef7d；模型
  m-a-p/YuE2-3B@1a96eca6；VAE b54118f0；数据集 e361b85a；patchset c1e04454…；
  cot=full，ode 32，9000/4096，VAE 1024+16，2 候选/prompt。
- provenance（`verify_provenance.py`，PR #16 树）：384 条 LEGACY 记录如实标注，
  **0 violations**（不升级、不混淆证据等级）。

## 5. Git 现场三方对照

| 树 | HEAD | 用途 |
|---|---|---|
| /workspace/YuE2-SGLang-ROCm | fee027d（fix/w7900-fresh-image-resume-hardening，clean） | Arm B 战役冻结检出（勿动） |
| /data/yue2/worktrees/joint-blog-rc | 66b5a13（integration/joint-blog-rc = PR #15 head） | RC 集成基线 |
| /tmp/opencode/rc2 | f6b24d7（mission/joint-blog-rc2 = PR #16 head，= origin） | RC2/RC3 工程分支 |

PR #16（Draft，MERGEABLE，base=integration/joint-blog-rc）：远端 head f6b24d7，
CI 2×SUCCESS（cpu-tests，run 44462151645 / 44462144306，2026-11-19）。

## 6. 必读资料核验

`reports/joint_blog_rc/rc2/` 下 10 份必读文件全部存在并通读；RC2_02 的闭合清单
（journal 重算 / audit FULL / provenance / 打分 rc=0 / 树 SHA / bundle manifest /
四指标对照 / G3 翻转）即本 RC3 的执行项——逐项执行结果见 01/02 系列。

## 7. 与历史基线的差异（如实记录）

- FINAL_REPORT_ZH（RC2 快照）D 表中 Arm A SongBench 6.7044 为**选样口径下的旧值**；
  本机磁盘现行 armA_wsb_full（fresh，armA_full_20261115f）实况为
  selected-192 Global=6.7417 / unselected-384 Global=6.7319。本报告一律以磁盘实况为准。
- Arm A 与 Arm B 的生成后端不同（torch-eager vs SGLang；见 01 科学一致性章节），
  对照结论以该差异为明示前提。
