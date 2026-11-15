# 02 — Destination No-Clobber RCA（P0-B）

## Before
`if dst.exists(): raise ... os.replace(tmp, dst)` ——检查与提交间存在竞争
窗口；`os.replace` 覆盖已有目标（含 symlink 目标被跟随替换）。

## Fix（copy_verified + atomic_publish.link_no_clobber）
提交原语改为 `os.link(2)`：内核级原子 no-clobber——对任何已存在路径形态
（常规/symlink/dangling）一律 EEXIST；tmp 必须与 dst 同目录（同文件系统由
构造保证，EXDEV fail-closed）；成功后 unlink tmp + fsync 父目录；失败路径
清理 tmp。另增**源 inode 身份检查**（dev/ino 前后比对）捕获同尺寸换文件。

## 测试（真实多进程，无 Mock exists()）
- 新目标→PASS；已有 file/symlink/dangling→拒绝且原样保留；
- **真实双进程×6轮同目标竞争：每轮恰一 WIN，败者输出 LOSE，胜者字节完整，
  无 `.partial-` 残留**；
- 跨目录 tmp→PublishError；
- 错误 expected sha→失败且 tmp 清零、final 不存在；
- 拷贝窗口内源被换 inode（同尺寸）→`source file identity changed`→不发布。
