# FINAL_REPORT_ZH — W7900-RC3 最终工程终报（2026-11-22）

> 覆盖 M1（Arm B 最终物理验收）、M2（PER 跨评测器科学验证）、M3（PR #16 工程
> 收口）、M4（GitHub 交付与二次独立审计）。全部结论以磁盘/GitHub 实况证据为准；
> 外部阻塞如实标注。

## A. Executive Verdict

| 裁定 | 值 |
|---|---|
| **ARM_B_VERDICT** | **COMPLETE — 384/384 FULL，四指标官方冻结评测器打分完成，独立复核一致** |
| **PER_PARITY_VERDICT** | **OPEN（BLOCKED_EXTERNAL_CUDA_HOST）**——A2/B2/C1/C2 未执行；本地侧 H4 已排除、H1 方向性证据增强（音素级删除主导），无平价声明 |
| **PR16_ENGINEERING_VERDICT** | **GO**——零开放可复现 P0/P1；精确 HEAD CI 绿；物理回归完成；协议不变量零变化。owner 合入决策保留 |
| **JOINT_PUBLICATION_VERDICT** | **NO-GO**——G9（作者批准）NOT_PRESENT、G4 OPEN、G10 NOT_PRESENT；工程 GO 不外溢为发布 GO |

## B. Exact Git State

| 项 | 值 |
|---|---|
| 会话初始 | 战役检出 fee027d（未触碰）；工程分支 f6b24d7（=远端 PR #16 head）；main ba99c4d |
| 最终本地 HEAD | `3adf91357011cde0b68a4b13432f0972fb392ddc`（mission/joint-blog-rc2，含收尾提交后见下） |
| 远端 PR #16 head | `3adf913…`（fetch 复核逐位一致；fast-forward，无 force-push） |
| base | integration/joint-blog-rc @ 66b5a13 |
| CI（精确 HEAD） | cpu-tests **2×SUCCESS**：[44987814341](https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/44987814341)、[44987809220](https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/44987809220) |
| PR 评论 | [#issuecomment-7074590938](https://github.com/AIwork4me/YuE2-SGLang-ROCm/pull/16#issuecomment-7074590938) |

## C. W7900 物理验证

- 硬件：AMD Radeon Pro W7900D（gfx1100，48 GiB）；ROCm 用户态 env B
  torch 2.12.0+rocm7.14.1 / env A 2.10.0+rocm7.1。
- Arm B 战役（run `armB_full_20261119T015756Z`，checkout fee027d）：
  2026-11-19 01:57 起，2026-11-20 09:34 生成完毕（wall 113 775 s ≈ 31.6 h，
  ≈296 s/候选，0 retry 0 fail），链自动完成 audit → 四指标 → done（20:31）。
- 审计：FULL；本会话独立重跑官方 verifier 输出与 chain 产物逐字节一致。
- Provenance：0 violations，384 LEGACY 如实标注；384/384 identity 重验证。
- 失败/恢复：战役自身零失败；本会话另做受控 SIGINT/SIGKILL 中断-恢复演练
  （隔离→重生成→精确 complete+resumed，audit PILOT 0 问题）。

## D. 官方基准对照（selected-192，磁盘实测）

| 指标 | 官方 | Arm A（torch-eager） | **Arm B（SGLang）** | B−官方 |
|---|---:|---:|---:|---:|
| SongBench Global | 6.7316 | 6.7417 | **6.7383** | +0.0067 |
| MuLan | 0.5068 | 0.4970 | **0.5092** | +0.0024 |
| AllMusicCaps | 0.4054 | 0.4010 | **0.4056** | +0.0002 |
| PER micro | 8.44% | 16.83% | **17.76%** [15.22, 20.63] | **+9.32 pp** |

科学注记：两臂为同 GPU 上两条独立实现路径，配对差 −0.016 pp
[−1.759, +1.561]（含 0）、ρ=0.871——「~+9pp PER」跨栈稳定；非 ASR 三指标
两臂均在官方 ±0.012 内。Q3O 未测（显存）。

## E. PER 跨评测器结果

| Cell | 状态 | 结果 |
|---|---|---|
| A1（Arm A 音频 × ROCm 评测器） | **本会话核验** | 16.83%（聚合+选样独立复算精确一致） |
| B1（Arm B 音频 × ROCm 评测器） | **本会话核验** | 17.76%（同上；1 个 PER 并列 tie-break 差异，聚合不变） |
| A2/B2（同音频 × 官方 CUDA 评测器） | **BLOCKED_EXTERNAL_CUDA_HOST** | kit 双臂就绪：Arm A 16.26 GiB + Arm B 8.62 GiB manifest 全量验证；Arm B 官方 prepare_inputs 384/384（1017 s）；verifier 加固（symlink/穿越 fail-closed，8/8 负控 + 4/4 变异） |
| C1/C2（作者参考音频） | **BLOCKED_EXTERNAL_AUTHOR_ASSETS** | 作者问询稿备好未发（owner 门） |

因果证据增量：音素级 I/D/S 分解（两臂 selected-192，逐候选 D+S+I 与官方
edits 断言一致）——**删除主导**（D 占 33.5–38.5%，I <10%），hyp/ref 音素比
0.947–0.960，两语言同向；与 H1（ROCm ASR 欠转录）方向一致、与 H2 不一致，
但不闭合。H4（本地协议不匹配）经独立复算排除。剩余不确定性：A2/B2 未执行；
H3（评测器漂移）待作者答复。

## F. PR #16 审阅与修复

| 缺陷 | 根因 | 修复 | 控制 |
|---|---|---|---|
| D1（P2）交接 verifier 接受 bundle 外同哈希 symlink；manifest id 可 `../` 穿越 | 仅 `is_file()`+内容哈希，无自包含/命名契约 | symlink 全拒收 + `wsb_\d{3}_r[01]_s\d{6}` 契约 + inputs 路径白名单 + 重复 id/索引不一致拒收 | 1 正向（真实 384 路径）+10 负向；3 定向变异全杀；真实 Arm B bundle 复验通过 |
| D2（P3）审计器截断计数 schema 敏感（Arm A 报 384，实际≈0） | dict{abc,semantic} 全 False 被 truthiness 计真 | `is_truncated()`（dict 按任一 stage、标量按 bool） | 4 语义测试 + truthiness 回退变异被杀 |

RC2 已有 8 项修复复读全部接受（含 resume 精确 complete —— 本次在真实 GPU 上
以 SIGKILL 撕裂→恢复验证）。观察项（不修）：score 超时只杀直接子进程（有界
重试兜底）；/tmp 历史测试 stub 残留。

## G. CI 与独立审计

- 本机 CI 范围 **388/0**（373 基线 + 15 新增）；guards 全过（tier1+tier2
  1813 窗、数值完整性 1883 叶 0 差、compileall、bash -n）。
- 硬件条件测试如实 NOT_TESTED-SKIPPED；其行为由真实 GPU 回归覆盖（smoke、
  官方 acceptance 流真实生成+优雅停机、中断-恢复、lock/VRAM 释放）。
- 二次独立审计：远端 SHA 一致、CI 实况 SUCCESS、推送 diff 无敏感内容
  （仅文件名字符串）、无二进制、冻结证据未改（audit 重跑逐字节一致）、
  选中/聚合复算一致、无 protocol 变化（configs 对 base 零 diff）。
  未发现虚假 PASS。本审计为 AI 二审，不冒充人类批准。

## H. 安全、许可与溯源

公开产物仅哈希/聚合/状态；两臂 bundle（含授权歌词表演）仅限 owner 授权的
私有通道，本会话零外发。历史 Git 对象处置仍为 owner 法律决策（选项 a/b/c）。
provenance LEGACY 不升级。Q3O/性能范围决定待 owner+作者。

## I. Release Gates（G1–G10，详见 04_RELEASE_GATE_LEDGER.json）

| Gate | 状态 | 一句话 |
|---|---|---|
| G1 | CONDITIONAL-PASS | 二审零开放 P0/P1；精确 HEAD CI 绿；待 owner 审阅合入 #16 |
| G2 | PASS | Arm A 384/384 + 复算 + 溯源 0 违规 |
| G3 | **PASS** | Arm B 384/384 FULL + 四指标 + 独立复核（本次翻正） |
| G4 | BLOCKED_EXTERNAL | 决定性单元外部阻塞；kit 双臂就绪 |
| G5 | PARTIAL | 三项历史运行时问题未获新证据；评测器有界化已修；预注册协议在 |
| G6 | PARTIAL | 三指标达标复现；PER OPEN；Q3O 未测 |
| G7 | PASS（含 owner 项） | guards 全过；历史对象决策开放 |
| G8 | PARTIAL | 命令矩阵 CPU 侧验证 + 本机物理回归；fresh-clone 端到端待独立执行者 |
| G9 | NOT_PRESENT | 作者消息未发 |
| G10 | NOT_PRESENT | 无 AMD 批准 |

## J. 剩余任务（仅证据支撑项）

| 优先 | 任务 | 责任 | 验收 |
|---|---|---|---|
| P0 | owner 审阅合入 PR #16 | owner | 合并（或附修改）；最终 HEAD CI 绿 |
| P0 | A2/B2 执行（CUDA 主机 + EXT-5 私有传输授权） | owner→CUDA 主机 | 预注册判读落档；G4 收口 |
| P0 | 作者消息外发（venue + 通道授权） | owner | 实发 + 回应落档（G9 素材） |
| P1 | M4 三项运行时 RCA 区分性实验（GPU 窗口） | 后续会话 | 04 报告更新 |
| P1 | M8.1 fresh-clone 复现（独立执行者） | 独立执行者 | RC2_07 清单全绿 |
| P1 | Q3O 范围决定 | owner+作者 | 显式接受 NOT_TESTED 或交接 |
| - | 历史 Git 对象处置 | owner（法律） | a/b/c 落档 |

## K. GitHub 交付实况

- PR：https://github.com/AIwork4me/YuE2-SGLang-ROCm/pull/16（head 3adf913）
- 修复提交：86355b3；证据提交：3adf913（+本终报收尾提交）
- CI：run 44987814341 / 44987809220（均 SUCCESS @ 3adf913）
- 报告路径：`reports/w7900_rc3/`（00–04 全系列 + 本文件）
- PR 终评评论：#issuecomment-7074590938

---

## Executive Summary（≤150 字）

Arm B 在 W7900D 真实完成：384/384 FULL、官方冻结评测器四指标打分齐备
（SB 6.7383/MuLan 0.5092/AMC 0.4056 贴近官方；PER 17.76% vs 8.44%），
独立复算与 provenance 全过。PER 差距新增音素级删除主导证据、本地协议排除，
但 A2/B2 CUDA 单元外部阻塞，维持 PER_PARITY_OPEN。PR #16 二审修复 2 缺陷
（交接 kit symlink 逃逸 P2、审计截断计数 P3），388 测试全绿、精确 HEAD CI
SUCCESS，已达 Engineering GO；联合发布仍需作者/AMD 批准与 G4 收口。
