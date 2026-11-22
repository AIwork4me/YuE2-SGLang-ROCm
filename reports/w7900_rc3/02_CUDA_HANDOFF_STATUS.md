# 02 — CUDA Handoff 状态（W7900-RC3）

## 结论

**READY_FOR_CUDA_EXECUTION（双臂齐备）+ BLOCKED_EXTERNAL_CUDA_HOST（执行）。**
W7900 为 gfx1100 ROCm 设备，不是 CUDA 主机；本会话未也绝不会在本机模拟 CUDA
scorer 或将 ROCm torch 称作 CUDA backend。以下全部为本机真实执行的结果。

## Kit（reports/joint_blog_rc/rc2/RC2_03_AUTHOR_CUDA_HANDOFF/）RC3 增量

| 项 | RC2 状态 | RC3 状态 |
|---|---|---|
| Arm A bundle manifest | 16.26 GiB / 4224 文件验证 | 复核通过（不变） |
| Arm B bundle manifest | 待战役完成 | **已生成并全量验证**：384 候选 / 4224 文件 / 8.62 GiB，全部 sha256+size 一致（armB_bundle_manifest.json 现于 /data/yue2/tmp/rc3_kit_validation/，随本次提交入 kit 目录） |
| 官方 prepare_inputs 验证 | Arm A 384/384 | **Arm B 384/384 PASS（1017 s）** |
| wsb_eval.py 直调（非 python -m） | 已修正 | 复核 runbook 无回归 |
| standard 全 bundle（非 mp3-only） | 已修正 | Arm B songs/ 结构 384×11 文件与 manifest 一致 |
| evaluation_inputs 相对路径布局 | 已修正 | Arm B 干净 report 目录实证 |
| 接收端 verifier | 4 种损坏模式拒收 | **安全加固**：symlink 逃逸拒收（此前缺陷：指向 bundle 外的同哈希 symlink 被接受）+ manifest id 严格命名契约（拒绝 `../` 穿越）+ inputs 路径白名单 `songs/<id>` + 重复 id/索引不一致拒收；8/8 负向控制 + 真实 bundle 正向 + 4/4 变异杀死（PR #16 新测试 15 个） |

## 阻塞项（执行 A2/B2 所需，均非本机可解）

1. **CUDA 主机**：任意满足 pinned 评测器要求的 NVIDIA CUDA 机器（H100/A100/RTX…）。
2. **owner 授权的私有传输通道**（EXT-5）：bundle 含授权歌词表演，禁止公开仓库；
   两臂合计 ~24.9 GiB。
3. （可选最优）作者侧 C1/C2 资产：参考音频或 per-song receipts。

## 接收端执行（无变化，双臂各自）

```bash
python verify_transfer_bundle.py --bundle armB_transfer --manifest armB_transfer/armB_bundle_manifest.json
python wsb_metrics/wsb_eval.py prepare --metrics per,songbench --install
python wsb_metrics/wsb_eval.py score --input armB_transfer/evaluation_inputs.jsonl \
       --output runs/armB_cross_scores_cuda --mode standard --metrics per,songbench
```

预注册判读：8–11% ⇒ H1；16–18% ⇒ H2；中间 ⇒ 配对共因子分解
（我方提供 prompt 级配对 JSON：03_PER_CROSS_ARM_INTERNAL.json + RC3 音素分解聚合）。

## 隐私与合规

- bundle（歌词表演 + 模型输出）仅限授权私有通道；公开仓库仅允许
  哈希/清单/聚合/脚本（本次提交物已过 public_evidence_guard + tier-1/2 扫描）。
- 本会话零外发；作者消息（RC2_06）仍为草稿，发送是 owner 门。
