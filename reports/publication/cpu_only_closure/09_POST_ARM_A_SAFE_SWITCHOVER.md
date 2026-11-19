# 09 — Arm A 结束后的安全切换方案（POST_ARM_A_SAFE_SWITCHOVER）

状态：**方案文档，当前不执行**。生成、审计、打分仍由正在运行的原始代码
（run-id `armA_full_20261115f`，驱动源 `8c242ba` 树）继续完成。本方案的任何
Gate 未满足前，禁止切换、禁止部署新驱动、禁止启动后续 GPU 任务。

## 背景

正在运行的 Arm A campaign 使用 `mission/w7900-fresh-image-final-closure @ 8c242ba`
树的驱动。PR #8/#10 与 C1 audit 分支已改进 journal/恢复/隔离/超时语义
（flock 串行、torn-tail 隔离 sidecar、内部损坏 fail-closed、uuid 隔离名、
worker 超时、孤儿复用、scope 校验、symlink 拒绝）。这些改进**不得**热替换进
正在运行的实验目录。切换只能发生在下述门禁全部满足之后。

## Gate A — 确认实验真的结束（不依据 ETA）

逐项留下机器可读证据后才算满足：

| # | 条件 | 证据形式 |
|---|---|---|
| A1 | 驱动进程自然退出（journal 收尾完成，无 `_gen_worker` 子进程存活） | `pgrep -af run_wsb_torch` 为空 + 驱动日志尾行 `[armA] finished pass: 384/384` |
| A2 | 无仍在写入的 candidate（`songs/*.partial` 数为 0 或全部已隔离） | `ls songs/ | grep -c partial` = 0 |
| A3 | Journal 完整且可解析（新驱动 `read_journal` 零问题，或问题全部有隔离 sidecar 对应） | 新驱动 dry-run 读取输出 |
| A4 | **384/384 官方审计 FULL**（`verify_wsb_artifacts.py --mode full` 退出 0 且 `verdict=FULL`；truncated-but-valid 计入） | `audit.json` |
| A5 | 失败/重试记录完整（journal 中 failed 记录均对应已恢复的 complete 或明示原因） | journal 统计脚本输出 |
| A6 | 原始代码 SHA 冻结（运行树 `git rev-parse HEAD` == 运行 `run_config.json` 记录的协议树；驱动源/worker sha 收据已在证据目录） | 冻结收据文件 |
| A7 | 证据已备份（journal/audit/run_config/songs sha 清单已复制到 evidence 并提交） | git 提交 |

**若 Arm A 仍在运行：绝不切换。** 若卡死（GPU 0% + journal 停滞 > 90 分钟 +
诊断快照已存）：先收集 `armA_stall_diagnostics.log` 类证据，再按原驱动的
graceful SIGINT 停止；即使如此，切换仍需重走 Gate A 全表。

## Gate B — 冻结原始实验

在只读目录生成冻结包 `/data/yue2-runs/armA_wsb_full_frozen_<ts>/`（复制，绝不动原件）：

- `run_config.json`（含 runtime/driver_protocol/worker sha 信息域）
- `generation_manifest.jsonl` 全量 journal + sha256
- `evaluation_inputs.jsonl` + sha256（与冻结 manifest 比对）
- 每 candidate 的 `result.json/request.json/config.json` + `audio.flac` 的
  sha256 清单（`find songs -name audio.flac | xargs sha256sum`）
- 驱动/worker 源码副本（运行树 `scripts/run_wsb_torch.py` + `_gen_worker.py`）
- 依赖收据（env A pip freeze + torch/HIP 探针输出）
- 日志（驱动日志、watchdog 诊断、mission_chain 各阶段日志）

冻结包生成后写 `FROZEN.md`（清单+每文件 sha），才允许进入 Gate C。

## Gate C — 测试新驱动（独立测试目录，不触碰冻结件）

新驱动 = C1 audit 分支树的 `run_wsb_torch.py`。全部 CPU 可测项先跑：

1. **Synthetic Resume**：用 Gate B 冻结包的副本（复制到临时目录）执行
   `run_wsb_torch.py --runs <copy>`：期望 `already_complete=384`、零生成、
   身份比较 PASS（volatile 字段差异被正确忽略；`driver_protocol` 一致）。
2. **Fault Injection**（C1 已有测试 + 面向冻结数据的定向注入）：
   - 删除某 candidate 的 `result.json` → 该候选失效并进入重生成队列（不虚假计数）
   - 篡改 journal 尾行（torn）→ sidecar 隔离 + 恢复后正确计数
   - 注入 journal 内部损坏 → fail-closed 拒绝续跑（人工审计）
   - symlink candidate → 拒绝
   - `--worker-timeout-s 1` + 睡眠 worker → 超时失败记录 + `.partial` 完整保留
3. **Crash Recovery**：kill -9 新驱动于第 N 个 candidate 中途 → 重启后续跑
   计数与 journal 一致（复用 C1 `test_c1_fault_injection` 流程于冻结副本）。
4. **Artifact Integrity**：对冻结副本跑 `verify_wsb_artifacts --mode full`，
   期望与 Gate A4 相同的 FULL 与相同的问题集（零、或已知 truncated 计数）。
5. **Source Identity Check**：新驱动写出的任何恢复/补生成记录都带新
   worker sha；历史 complete 记录不被重写（journal 只追加）。

全部通过后，**才**安排一次 W7900 物理回归（单 prompt 生成 + 官方 verify），
作为 Gate C 的最终项。物理回归仍不修改原实验目录。

## Gate D — 启动后续任务（明确不在本 CPU-only Mission 内）

前置：A/B/C 全绿 + owner 对切换的明确批准。顺序：

1. 新驱动独立硬件回归（同 Gate C.5，正式记录）
2. Arm A 打分链（PER→SongBench→MuLan/AMC，单 GPU 串行，`mission_chain` 已就绪）
3. Arm B 新镜像全量复现（server 验收 → 384 campaign → 打分）
4. SGLang AR Hang RCA（P5.2，服务器日志+栈采样+最小复现）
5. HIP Illegal Memory Access 独立复现（P5.3，仅在无活动证据生产时）
6. `YuE2Pipeline.close()` 内存行为调查（P4.1 遗留项）
7. PER Cross-Evaluator A/B（P6.3 受限执行包流程）

**本 CPU-only Mission 不得自动触发以上任何 GPU 任务。**

## 回滚

切换后若新驱动出现未知行为：停止条件回到 Gate A 语义（驱动退出+journal
稳定），重新启用冻结包数据；原始 8c242ba 树驱动始终可用（git 可达）。
