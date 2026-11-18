# 07 — CI 与回归结果（C1 P5）

## 本地完整执行（真实命令与结果）

```bash
python -m compileall -q scripts supervisor        # OK
bash -n scripts/*.sh                              # OK
python scripts/public_evidence_guard.py           # PASS (working-tree gate)
python scripts/evidence_lyrics_detector.py        # PASS 257 files (tier1+tier2)
python scripts/verify_numeric_receipt_integrity.py  # PASS 0 drift (fail-closed verified: bad ref -> exit 2)
python -m pytest tests -q --ignore=<3 hardware suites> -ra --strict-markers
  # CI 等价（无 workspace）：136 passed / 26 skipped / 0 failed
  # 本机（YUE2_WORKSPACE=/data/yue2）：162 passed / 0 failed（含修复后的 test_wsb_full_mode 12/12）
```

## 修复链证明（Before FAIL → Fix → After PASS → Controls → Regression）

| 缺陷 | Before | Fix | After | 负向对照 | 回归 |
|---|---|---|---|---|---|
| detector 无真值层/扩展名绕过/短文本/嵌套/音素数组 | 旧 guard 全漏（矩阵 main=1637 发现仍可达） | `evidence_lyrics_detector.py` 双层 | 13/13 合成测试过 | 伪造泄漏 12 类全被抓；`gfx1100`/数值 phonemes 不误报 | CI 每次运行 |
| 数值完整性无程序化验证 | 无工具 | `verify_numeric_receipt_integrity.py` | PASS 0 漂移 | bad `--orig-ref` → exit 2 | CI（fetch-depth 0） |
| journal 崩溃一致性仅字符串断言 | （PR10 已修实现，测试薄） | `test_c1_fault_injection.py` 真实 SIGKILL/并发/超时 | 12/12 过 | torn/内部损坏/越界 id 全阻断 | 本地+CI |
| test_wsb_full_mode fixture 缺 identity/config（CI 盲区：从未真跑） | **8c242ba 即 5 failed**（预先存在，非 PR8/10 回归） | fixture 自洽 identity + 断言对齐真实报文 + 新增 forged-identity 负向对照 | 12/12 过 | `identity_mismatch` 注入被抓 | CI（有 manifest 的机器全绿） |
| G1 空 freeze 收据 | 2 文件 0 字节 | 根因=uv venv 无 pip；`uv pip list` 重生成（232+76 包） | 5/5 非空 | — | 收据入库 |
| README 字面 `\n` / 历史标注 | 渲染缺陷 | 修复+标注 | 视检过 | — | docs_contract CI |

## GitHub CI（最终 HEAD）

- Push run: https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/43682957300 **success**
- PR #10 event run: https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/43682960115 **success**
- （本文档所在提交的 CI 见最新 run；docs-only 变更，预期同绿）

## 仍需硬件/数据/授权的任务（诚实清单）

1. Arm A 384/384 完成+官方审计+四指标打分（GPU，进行中）
2. Arm B 新镜像复现（GPU，Gate D）
3. SGLang AR Hang 根因（GPU+服务端日志）
4. HIP illegal-memory-access 独立复现（GPU，空闲窗口）
5. `close()` 显存行为（GPU）
6. PER 跨评测器 A/B（官方 vLLM 参考环境 / 作者协作）
7. 磁盘不足路径的真实注入（硬件窗口）
8. 上游提交 ×3（Owner 批准）

## 最后独立审阅增加的检验

- `tests/test_numeric_receipt_integrity.py`：原始数值等价 + ASR repeat 计数漂移 + 两侧 ID 异常 + snapshot 数值路径缺失 + 布尔类型混淆。
- `tests/test_evidence_detector_integration.py`：独立临时 Git 仓库、原创英文合成歌词、非白名单文件扩展名、匹配命中/移除后的正反对照、无真实歌词输出、无 Manifest 的发布门禁、不可读文件与恶意 CSV。
- 将旧 `or True` vacuous tests 改为真实断言；Worker symlink guard 使用 AST 实际运行。
- 最新 CI 应严格以 PR HEAD 对应的 Push/PR Action URL 为准（运行结果不得用本文档生成前的旧 HEAD 假充）。**真实 Manifest 的 Tier 2 未在公开 CI 执行**，这不是数据集扫描 PASS。
