# 01 — PER 样本分类 RCA（C2 P1）

## 缺陷（Before，可复现）

`scripts/build_per_reference_package.py` 旧实现：

```python
emptyish = [r for r in sel_rows if r["metrics"]["per"]["per"] >= 0.999]
... bucket(emptyish, "empty_transcript")
```

**错误本质**：PER 是编辑距离错误率（可 >1），PER≈1 完全可能来自非空但全错的
转写；以 PER 阈值判定"空转写"是科学语义错误——会把"唱错/识别错"样本标成
"无输出"，污染跨评测器研究的分层。

## 根因

公开数值收据删除了转写文本后，"空"失去了直接证据；实现者用 PER 阈值做了
**替代性推断**——恰是 mission 原则"不得从缺失字段推断"违例。

## 修复（After）

新模块 `scripts/sample_classification.py`（单一事实来源，per_tail_analysis
与打包工具共用）：

| 状态 | 判定依据 |
|---|---|
| `EMPTY_CONFIRMED` | 选中 ASR repeat 的 text 字段**存在且为空白**；收据含 transcript_sha256（供受限原件核对）+ selected_asr_repeat + per |
| `NONEMPTY_CONFIRMED` | text 存在且非空（PER=0/1/>1 均可） |
| `EMPTY_UNKNOWN` | 收据无转写文本（公开数值收据的**正常态**） |

- 标签 `ASR_CAPPED / HIGH_PER / LANG_*` 与 empty 状态**显式可交叉**；
  LANG 缺失→`LANG_UNKNOWN`（不从缺失推断 False）。
- 分层桶：`empty_confirmed`（仅证据样本）/ `per_ge_0_999_empty_unknown`
  （PER≥0.999 且转写未知——如实命名）/ `asr_capped` / `high_per` /
  `lang_zh|en`；语言桶不再要求转写确认。
- 统计守恒 `assert_conservation`：384/192/每prompt 2 候选/selected 恰192/
  坐标唯一——fail-closed。

## 测试（tests/test_c2_classification.py，14 个，全过）

负向对照覆盖 mission 3.4 全部 10 项：PER=1 非空→NONEMPTY；PER=1 空→
CONFIRMED（含收据）；PER=1 未知→UNKNOWN；PER=0 非空；PER>1；ASR 截断标签；
语言缺失→LANG_UNKNOWN；重复候选→拒绝；selected 不完整→拒绝；证据 source_sha
不匹配→收据如实携带但不产生 CONFIRMED。

**验收达成**：无直接转写证据的样本一律不可能被标 EMPTY_CONFIRMED。
