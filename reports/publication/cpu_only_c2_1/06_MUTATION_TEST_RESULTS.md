# 06 — 变异控制结果（P1-B.3，scripts/mutation_controls_c21.py）

隔离树（tempdir 复制，不触碰分支）× 5 变异 × 3 测试文件（-x 早停）：

| 变异 | 内容 | 结果 |
|---|---|---|
| M1 | 删除快照 symlink guard | **KILLED**（1 failed） |
| M2 | no-clobber→os.replace | **KILLED**（1 failed） |
| M3 | 跳过 encoding.mp3↔row 绑定 | 首轮 **SURVIVED → 暴露真实测试缺口** → 补 `test_encoding_receipt_not_bound_to_per_song_row_fails`（收据互换场景）→ **KILLED** |
| M4 | 跳过 session 收据验证（信任 journal） | **KILLED**（1 failed） |
| M5 | 跳过 post-copy 源哈希 | **KILLED**（1 failed） |

**5/5 KILLED**。M3 的存活-修复-击杀正是变异控制的目的：证明每条安全契约
都有测试守卫，而非凑数。
