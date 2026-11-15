# 00 — 基线与安全边界（C2）

执行：2026-11-15T07:22Z 起 · 工作目录 `/workspace/YuE2-C2-CPU-Audit`（独立clone）
分支 `mission/c2-scientific-provenance-hardening`，基于 PR #10 实时 HEAD。

## 实时基线（gh/git 实测，非转述）

| 项 | 值 |
|---|---|
| PR #10 head | `8756125`（较 C1 结束时的 `350b2ee` 前进 11 个提交：tier-2 英文歌词扫描、数值校验加固、空洞断言清理、文档对账——已逐一审阅，无与本 mission 冲突的语义） |
| PR #10 CI | run 43688325738 success（153 passed/28 skipped/0 failed） |
| PR #7 | MERGED（main=`ba99c4d`） |
| PR #8/#9 | Draft 未动 |
| 工作树 | clone 后 0 未提交 |
| Arm A（只读） | 启动时 33/384；driver 16537 ALIVE；本 mission 全程零 GPU 命令、零运行目录修改 |

## 安全边界执行记录

- 所有测试：CPU + tmp_path + 合成数据（合成音频字节/合成manifest/Mock worker）。
- 唯一触碰的"真实"文件：冻结评估器源码**只读**（确认 `audio_sha256`=MP3 哈希、
  `selected_candidates` 官方 schema——`wsb_eval.py:290-313,355`），零修改。
- 禁止清单（P0）逐项遵守；见 FINAL_REPORT 第13问。
