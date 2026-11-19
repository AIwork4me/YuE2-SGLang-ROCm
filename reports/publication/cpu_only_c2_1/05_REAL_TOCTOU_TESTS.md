# 05 — 真实 Mid-Copy TOCTOU 测试（P1-B.1/.2）

## 替换的弱测试
旧 `test_copy_detects_midcopy_source_mutation` 实为"复制前变更"（Before-copy）。
保留其行为但改名语义；新增两组**真 mid-copy**：

1. `test_continuous_mutation_during_copy_detected`：96MiB 源；**确定性屏障**
   （轮询 `.partial-*` 出现=已过 pre-hash 进入拷贝窗口）后才启动连续
   pwrite 尾部改写直到 copier 退出——捕获输出必须含 `mutated`、dst 不存在、
   交付目录为空、flips>0（对抗写手真实运行）。无随机 sleep。
2. `test_inode_identity_change_detected`：线程内 copy_verified；`.partial-*`
   出现后同尺寸**换 inode**重写源 → dev/ino 检查命中 `identity changed`，
   不发布。

## 无效断言清扫（P1-B.2）
- AST 扫描全部测试：BoolOp(Or)含 Constant(True) → **0 处**（C1 后期已清）；
- 权限断言去空泛化：`not (mode & IWUSR) or mode & 0444`（0444 恒真=空泛）→
  改为精确 `mode & 0o222 == 0`（变异为可写实现时必失败）。
