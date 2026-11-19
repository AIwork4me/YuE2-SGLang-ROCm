# 03 — 生成源码溯源设计（C2 P3）

## 缺陷（Before）

驱动无条件 `worker_path.write_text(GEN_WORKER)`：
- 恢复历史 Run 时**覆盖**保存的旧 Worker 源码；
- 驱动升级后 `_gen_worker.py` 只留最新版——历史候选无法证明用哪份代码；
- Run 级单一 worker SHA 不足以支撑逐候选归因。

## 设计（After）

```
run/
  worker_sources/<worker_sha256>.py     # 内容寻址、O_EXCL、0444、写后自校验
  provenance/driver_sessions/<sid>.json # 每次驱动启动：driver sha + worker sha
                                        # + python/torch/gpu 环境收据（一次探测，
                                        #   避免384次torch import的数小时开销）
  provenance/<candidate_id>/
      <attempt_id>.launched.json        # 执行前（O_EXCL）：attempt uuid、双 sha、
                                        #   session、seed、坐标、时间
      <attempt_id>.result.json          # 执行后（O_EXCL）：complete/failed、wall、
                                        #   audio_seconds、identity
  generation_manifest.jsonl             # complete/failed 记录追加 attempt_id、
                                        #   worker/driver sha、session_id
```

执行文件=快照本身（内容即名字）；legacy `_gen_worker.py`：
- 内容不同→**原样保留**并另存为其自身 sha 的快照（不执行、不覆盖）；
- 首次新 Run→按旧惯例写一份（write-once）供旧工具读取。

## Stable vs Implementation（回答 mission 5.4）

- Stable Experiment Identity（run_config 比较域）：dataset/model/VAE sha、
  协议、backend、seed、`driver_protocol`——resume 严格一致。
- Implementation Provenance（信息域+逐attempt）：driver/worker sha、
  python/torch、session/attempt id——**同 Stable 可不同代码版本**，journal
  只追加，历史记录永不重写新 sha。

## 校验器 `scripts/verify_provenance.py`

逐 journal 记录判定：
- `PROVENANCE_VERIFIED`：launched+result 收据齐全、双 sha 与 journal 一致、
  快照存在且哈希自证（symlink 快照=violation）；
- `LEGACY_PROVENANCE_INCOMPLETE`：无 attempt_id 的历史记录——仅当 legacy
  `_gen_worker.py` 哈希==run_config 记录时给 `LEGACY_RUN_LEVEL_VERIFIED`
  归因，否则 UNKNOWN（**绝不虚构历史 sha**）；
- `PROVENANCE_VIOLATION`：伪造 journal sha、收据缺失/冲突、重复 attempt_id、
  崩溃窗口（launched 无 result）→ exit 1。

## 测试（tests/test_c2_provenance.py，18 个）

快照 write-once/同内容复验/篡改检测/新内容不改写旧快照/legacy 异内容保留/
symlink 拒绝 · 收据 O_EXCL · 校验器：干净通过/legacy 如实/legacy 失配=UNKNOWN
（非violation）/伪造 sha=violation/崩溃窗口=violation/重复 attempt=violation/
快照缺失=violation · 源级：journal 带溯源字段、执行用快照路径、校验器只读。
