# 01 — 整包发布原子性 RCA（P0-A）

## Before（可复现）
旧实现在 `--out` 直接逐候选复制：候选D身份失败时 A/B/C 已留在目标目录——
半成品可被误认为完整交付（测试：`test_candidate_failure_leaves_no_final_package`
在旧代码上 final 存在——见 08 号 Before 记录）。

## 根因
缺少事务边界：交付物逐文件可见，无单一提交点；`os.replace` 类提交还会覆盖。

## Fix（scripts/build_per_reference_package.py + scripts/atomic_publish.py）
- 全部产物写入**兄弟 staging 目录** `<out>.staging-<uuid>`（同文件系统）；
- 音频复制→jsonl/json 逐文件 fsync→**Package Completeness Audit**（逐文件
  重哈希+字节数+文件集相等）→`.package_audit.json` 标记；
- **单次原子提交**：`renameat2(RENAME_NOREPLACE)`（本机 overlayfs 与 CI ext4
  实测支持；不支持时 PublishError fail-closed，绝不退化 os.rename）；
- 任一步失败：`abort()` 销毁 staging（音频字节不外泄），final 不存在；
  crash 现场只可能留下 `.staging-<uuid>` 孤儿（命名清晰，永不冒充正式包，
  `test_staging_interrupted_leaves_no_final` 证明后续发布不受阻且不混入）。

## 负向对照（tests/test_c2_1_fail_closed.py，全部真实执行）
首/中/末候选失败→final 不存在且 staging 清零 · 既有完整包二次发布→字节
不变（前后全树哈希对比）· final 为 symlink→拒绝 · **真实双进程发布竞争→
恰一胜者+审计标记完整+败者零残留** · ENOSPC（json.dump 注入）→abort ·
staging 中断→不产生 final、后续发布成功且不混入孤儿内容 · staged 漂移
（audit 阶段哈希）→拒绝。
