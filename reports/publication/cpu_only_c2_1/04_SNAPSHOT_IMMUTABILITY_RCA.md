# 04 — Worker Snapshot 不可变性 RCA（P1-A）

## Before（4d9f4a2 缺口）
- symlink 检测靠哈希失配——**内容正确的 symlink 被接受**（路径即受控状态，
  类型必须先行）；
- 直接 O_EXCL 写最终名：崩溃可留下部分内容的"合法文件名"。

## Fix（run_wsb_torch._verify_snapshot_file / _publish_snapshot）
- **类型严格验证**：先 `is_symlink()` 拒绝（无论目标内容哈希是否正确），
  再要求 regular file，再字节哈希；
- **崩溃安全写入**：内容写 `.snap-tmp-<uuid>` + fsync → `os.link` 原子
  no-clobber 发布到内容寻址名；竞争败者内容一致性由验证兜底；崩溃只可能
  留 tmp 名（非 .py 后缀，永不冒充快照）；
- legacy 异内容/损坏源：原样保留+按其自身哈希快照（不执行）；
  `worker_sources` 为 symlink→拒绝（目录逃逸）。

## 负向对照（新增/强化 10 项）
**正确内容 symlink→拒绝（标题案例）** · 错误内容 symlink→拒绝 · 快照被篡改→
拒绝 · 名对字节错→拒绝 · 快照路径是目录→拒绝 · **真实双进程同 SHA→恰一份
快照+零 tmp 残留** · **fork 双进程异 SHA→三快照共存互不覆盖** · 崩溃写残留
tmp→后续正常+tmp 保留取证 · 损坏 legacy 保留 · worker_sources symlink 拒绝。
