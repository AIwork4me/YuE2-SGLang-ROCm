# 07 — CPU 回归与故障注入（C2 P6）

## Required Checks（真实执行，2026-11-15，分支 HEAD）

```bash
python -m compileall -q scripts supervisor   # OK
bash -n scripts/*.sh                         # OK
python -m pytest tests -q --ignore=<3 hardware suites> -ra --strict-markers
    # 集成 dry-run 树：197 passed / 26 skipped / 0 failed
python scripts/public_evidence_guard.py      # PASS
python scripts/evidence_lyrics_detector.py   # PASS 281 files (tier1+tier2)
python scripts/verify_numeric_receipt_integrity.py  # PASS 0 drift
```

## C2 新增测试（61 个，全部合成数据）

| 套件 | 数 | 覆盖 |
|---|---|---|
| test_c2_classification.py | 14 | P1 全部负向对照（见 01 文档） |
| test_c2_audio_identity.py | 11 | 真实文件复制/哈希/篡改/穿越/symlink/覆盖/权限（见 02） |
| test_c2_provenance.py | 18 | 快照/收据/校验器/崩溃窗口/伪造（见 03/04） |
| 升级 test_per_tail_analysis/_reference_package | 18→ | 4 元组 API+分层枚举+打包新契约 |

修复链（Before FAIL→Fix→After PASS→Negative→Regression）实例：
1. PER≥0.999→"empty"：Before=误分类可复现（旧 bucket 名）→Fix=分类模块→
   14 个负向对照→CI 回归（detector/guard 无关性+套件绿）。
2. 选择过度声明：Before=缺字段仍 VERIFIED（可复现：删 audio_sha256 字段）
   →Fix=分层→After=IDENTITY_INCOMPLETE→负向=坐标层禁止打包。
3. 音频身份：Before=换 flac 后包仍"合法"（复现于测试）→Fix=五链→负向=11 分支。
4. Worker 覆盖：Before=write_text 覆盖（复现：两次不同 GEN_WORKER）→Fix=快照
   →负向=篡改/symlink/伪造收据。

## 故障注入清单（mission P6 对照）

SIGKILL✓(C1#1 仍绿) · Torn Journal✓ · Missing Receipt✓(provenance) ·
Inconsistent Hash✓(audio+provenance) · Wrong Candidate✓(selection) ·
Symlink✓(audio+snapshot) · Existing File Collision✓ · Concurrent Writers✓(C1) ·
Read-only Artifact✓(导出0444+源只读读) · Permission Error✓(O_EXCL=EEXIST) ·
Interrupted Copy✓(TOCTOU+partial tmp) · Partial Output✓(整包拒绝)。

## CI Skip 分类（26 个，逐项）

| 类别 | 数 | 说明 |
|---|---|---|
| Official Manifest Required | 26 | test_wsb_full_mode(12+2 新增)+test_verify_wsb_artifacts(12)：需冻结 reproduction_manifest（校验真实协议文件）；CI 无数据集=诚实跳过。**已在本机带 manifest 全绿**（162+ 含 C2 后 197 集成树验证） |
| GPU Required | 0（套件整体被 ignore，不计 skip） | hardware-class 明确排除于 CPU CI |
| Third-party Evaluator Required | 0 | — |
| Environment-specific | 0 | — |
| Fixable With Synthetic Fixture | 0 | manifest 类 skip 不伪造官方数据（mission 禁止） |

## 限制（如实）

- 源文件在拷贝中被外部进程同字节替换（哈希不变）超出哈希链能力——已在
  02 文档注明（威胁模型外）。
- 磁盘满/权限只读根目录等 OS 级注入未做（需专用环境；记录为限制）。
