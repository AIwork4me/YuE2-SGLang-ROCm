# 01 — PR #7/#8/#9/#10 冲突矩阵（C1 实测）

方法：`git diff` 逐 PR 与 base 对比 + 语义标记扫描（非仅文件名重叠）。
驱动行为标记矩阵（`scripts/run_wsb_torch.py`）：

| 行为 | PR #8 head | PR #10 head(78c5cb8) | 结论 |
|---|:-:|:-:|---|
| flock journal 串行 | Y | Y | 同源设计，PR10 继承 |
| torn-tail 隔离 sidecar | Y | Y | 同上 |
| 内部损坏 fail-closed（raise） | – | **Y** | PR10 独有，采纳 |
| failed-after-complete 失效（最新状态胜出） | – | **Y** | PR10 独有，采纳 |
| uuid 隔离名（防同秒覆盖） | Y | Y | 同源 |
| worker 超时（--worker-timeout-s） | Y | Y | 同源 |
| 孤儿已验证产物复用 | Y | Y | 同源 |
| journal id 越界 scope 校验 | – | **Y** | PR10 独有 |
| symlink 拒绝（worker+resume） | 部分(仅rename) | **Y** | PR10 更完整 |
| GPU ownership lock（gpu_lock） | – | **Y**（承自 PR#9/C1-session1） | 保留 |
| 稳定/易变身份分离（VOLATILE_KEYS） | – | **Y**（承自 PR#9 修复） | 保留 |
| driver_protocol 语义版本 | – | **Y** | PR10 独有，采纳 |

## 覆盖关系判定

1. **PR #8 ⊂ PR #10（驱动行为）**：PR8 的 6 项行为标记全部存在于 PR10，
   PR10 另有 6 项增强。PR8 的驱动 diff（205 行改动）被 PR10 的实现
   完全覆盖。**不 cherry-pick PR8 代码**。
2. **PR #8 的 8 个测试为互补价值**（PR10 树缺失）：C1 已将其语义移植进
   `tests/test_c1_fault_injection.py::TestPr8ComplementaryPorts`（4 个移植
   测试，适配 PR10 API；其余 4 个语义已被 C1 故障注入测试覆盖——见
   04 号文档映射表）。PR #8 可标记 **Superseded by #10**（附本矩阵）。
3. **PR #7 与 #10 无实现冲突**：PR7 只动 evidence 文件 + 新增
   guard（base=main），PR10 base=mission 分支；两者对 evidence 的处理
   语义一致（删除原始文本、保留数值收据）。合并顺序建议：#7 → main
   先行（安全优先），#10 → mission 分支随后（其 base 含 8c242ba 的
   redacted 副本，#10 删除之改用数值收据——语义连续）。
4. **PR #9 与 #10**：#10 基于 #9 head，线性延伸，无冲突。#9 保持 Draft
   （Arm A 正在用其代码运行，不得因 CPU 工作标记 Ready）。
5. **C1 audit 分支（本分支）**：基于 78c5cb8，将 fast-forward 推回
   `fix/w7900-cpu-only-risk-closure-20261115`（PR #10 head）——无新分叉。

## 必须保留 / 必须删除

- 保留：PR10 全部驱动语义（上表）；PR9 的 gpu_lock/身份架构；PR7 的
  guard 思路（已被 C1 detector 扩展为双 tier）。
- 删除：无（无互相覆盖的坏实现；PR8 驱动 diff 随 Superseded 处置）。
- 重复测试清理：PR8 的 8 个测试在 PR8 分支保留即可（其分支冻结）；主线
  以 C1 移植版为准。
