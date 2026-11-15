# 08 — 科学证据不变性（C2 P7）

## 冻结面（C2 前后零改动，机器可核）

| 冻结项 | 验证方式 | 结果 |
|---|---|---|
| Model/VAE/Dataset/Evaluator revision+sha | configs/benchmark.lock.yaml 集成 diff | **零改动**（vs main 差异=main 缺文件的纯新增） |
| 协议锁（seeds/candidates/budgets/selection 定义） | 同上 + per_tail_analysis 官方选择逻辑仅收紧未放宽 | 零改动 |
| 192 prompts/384 候选身份 | `verify_numeric_receipt_integrity.py`（CI 每次） | PASS（24 行/19 身份字段/1851 数值叶零漂移） |
| 历史四指标（SongBench/MuLan/AMC/PER 17.77%） | 同上 + 文档未改 | 不变 |

## 变更面（只增不改性）

- 新增 Provenance 元数据（快照/收据/session/attempt）——**观测性**，不进入
  任何评分计算；
- 分类/分层验证只影响**声明与标签**的诚实度（EMPTY_UNKNOWN、COORDINATES 层），
  不触碰 edits/phonemes/PER 数值或选择规则；
- `assert_conservation` 是断言不是变换：384/192/2-per-prompt/selected-192
  在任何标签下守恒（测试证明标签不改变总数与加权合计）。

## 明确声明

**C2 changes experiment observability and correctness guards, not measured
model quality.** 历史 PER 17.77% vs 官方 8.44% 的差距依旧开放，需
P6.3 受限跨评测器实验（真实 ASR 对照），C2 未也无法在 CPU 上"解决"它。
