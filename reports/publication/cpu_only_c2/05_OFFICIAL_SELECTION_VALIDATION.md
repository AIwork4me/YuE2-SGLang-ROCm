# 05 — 官方 Selection 分层验证（C2 P4）

## 缺陷（Before）

`per_tail_analysis.choose_rows` 仅在**两侧都有字段时**比较 seed/audio_sha256；
字段缺失→跳过比较→仍标 `OFFICIAL_SELECTED_CANDIDATES_VERIFIED` ——**过度声明**。

## 官方 Schema 事实（wsb_eval.py:355，冻结源码）

```python
result['selected_candidates'] = [{'prompt_index': ..., 'candidate_index': ...,
                                  'seed': ..., 'audio_sha256': ...} for r in selected]
```

官方契约**本就含全部四字段**；缺字段=对官方格式的偏离，必须报告而非默认接受。

## 分层验证（After）

| 枚举 | 语义 |
|---|---|
| `OFFICIAL_SELECTION_AUDIO_IDENTITY_VERIFIED` | 192 项 seed+audio_sha256 **全部在位且逐一匹配**候选收据（唯一可发表级） |
| `OFFICIAL_SELECTION_COORDINATES_VERIFIED` | 坐标+seed 匹配但 audio 身份字段缺（只证"选了谁"，不证"音频版本"） |
| `OFFICIAL_SELECTION_IDENTITY_INCOMPLETE` | 部分字段缺失（missing_fields 列出前 8 项） |
| `INVALID_SELECTION`（以 ValueError 实现） | 任何失配/重复/形状不完整/越界 |

输出新增 `selection_field_audit`：seed_verified / audio_sha256_verified 计数 +
missing_fields + schema_note。`publication_grade_selection` 仅在
AUDIO_IDENTITY_VERIFIED 层为真。打包工具要求该层（坐标层→拒绝导出，测试覆盖）。

## 两个科学门禁的分离（mission 6.4）

"官方选了哪个候选"（坐标/seed 层）与"该候选音频是否验证为正确版本"
（audio_sha256 层+P2 身份链）现各自独立断言——任何一层未闭合都不再冒名。

## 测试

`test_official_selection_verifies_sha_and_seed`（升级：断言 192/192 计数+
错 sha 拒绝）· 打包侧 `IDENTITY_INCOMPLETE summary 阻止发表级打包` ·
既有 tie/missing/dup/seed-mismatch 边界（C1 gap 探针已固化于测试）全部仍绿。
