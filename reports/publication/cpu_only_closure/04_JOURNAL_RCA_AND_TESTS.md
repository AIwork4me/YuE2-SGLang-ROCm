# 04 — Journal RCA 与故障注入测试（C1 P2 实测）

对象：PR #10 head(78c5cb8) 的 `run_wsb_torch.py` journal/恢复/隔离/超时实现
（与 PR #8 的语义对比见 01 号文档）。

## 故障注入执行记录（真实进程，非字符串断言）

`tests/test_c1_fault_injection.py`（12 测试，全过）：

| # | 场景 | 方法 | 结果 |
|---|---|---|---|
| 1 | **SIGKILL 击中写入中** | 真实子进程循环 append，稳定后 `os.kill(SIGKILL)` | 恢复读取零虚假计数；尾行撕裂则 sidecar 隔离 |
| 2 | **并发写竞争** | 2 真实进程 ×40 记录同时 append | 80/80 记录完整无损（flock 串行生效），problems=[] |
| 3 | torn 尾后 append | 直接构造半行 → append | append 以 ValueError 拒绝（fail-closed）；先恢复后 append 正常 |
| 4 | 内部损坏 | 中行垃圾 | read_journal raise"manual audit"，续跑被阻断 |
| 5 | complete→failed | 同 id 两事件 | 最新状态胜出，complete 集合剔除 |
| 6 | **worker 超时路径** | subprocess.run(timeout=2) 杀睡眠 worker | 超时真实发生（<20s）、`.partial` 原样保留、无孤儿进程存活 |
| 7 | 隔离名唯一性 | 同秒 5 次重试隔离 | uuid 命名 5/5 唯一，先前的隔离证据全保留 |
| 8 | journal 越界 id | scope 谓词实测 | 外来 id 集合可被判非子集（驱动用其拒绝续跑） |
| 9-12 | PR#8 移植：symlink 拒绝（源码+resume 双路径）、无 rmtree、schema 无效的 complete 记录阻断 | 适配 PR10 API | 全过 |

## mission 4.1 清单对照

完整写入✓(flock+fsync+写循环) / 不完整尾行✓ / 损坏中间行✓(raise) /
fsync✓ / 并发✓(实测#2) / 重复候选✓(dedup) / Complete→Failed✓(#5) /
Failed→Complete（重生成后追加 complete，最新胜出语义✓）/ 缺失 Journal✓
(空集) / Journal 与产物冲突✓(resume_verified_candidate 以 verify_result
为准，声称完成但损坏→失效并重生成) / 损坏产物恢复✓ / 残缺隔离✓ /
历史证据保留✓(uuid 隔离名不覆盖) / 磁盘不足（驱动 MIN_FREE_GB 门，属
运行路径，CPU 侧为参数断言）。

## mission 4.2 Worker Timeout 审阅结论

- 正常终止：subprocess.run 超时→SIGKILL 子进程并等待回收；worker 是叶子
  进程（无再下层子进程）→ 无遗留。实测#6 证实无孤儿。
- `.partial` 完整保留（超时被记为 failed+原因；下次尝试走隔离）。
- 不重复计数：failed 记录不进 complete 集；重生成成功才追加 complete。
- 长歌曲安全：默认 10800s ≫ 实测单候选 ~700s 均值（历史最长 <30min）。
- **明确不宣称**：该超时不等于 SGLang AR Hang（server 端问题）的解决——
  两者所有权不同（本驱动是 native PyTorch arm 的进程边界管理）。

## mission 4.4 身份与溯源

- Stable contract：model/VAE/manifest sha、生成参数、`driver_protocol`
  （armA-driver/1）→ resume 严格比对。
- Per-attempt provenance：driver/worker 源 sha 为信息域（记录不比对）；
  journal 每条 complete 含官方 identity（request/config/weights blob 哈希）
  → **候选级代码溯源**可经 result.json+config.json 复核；恢复记录
  （recovered_from_verified_artifact）单独标记，不冒充生成记录。
- 源码升级不回写历史：journal 只追加；旧 complete 不被新 sha 重写。

## 遗留（诚实）

- 驱动对 read_journal 的 raise 以 traceback 退出（非优雅错误码）——可接受
  （fail-closed 语义正确），改进项记入后续。
- 磁盘不足路径仅有参数级 CPU 覆盖（真实低磁盘注入需硬件窗口）。
