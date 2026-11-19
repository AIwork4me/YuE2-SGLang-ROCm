# 08 — 上游归属（C1 P6.5 范围）

本 Mission 仅处理 AIwork4me 自有问题；未提交任何 SGLang/YuE/WildSongBench
上游 PR/评论。

| 议题 | 归属仓库 | C1 动作 | 上游提交门禁 |
|---|---|---|---|
| torch-eager allowlist（0010） | m-a-p/WildSongBench | 静态复核：补丁+RCA+正反测试+链式哈希验证齐备；许可证兼容（Apache-2.0 侧改动仅一行 allowlist） | 等 Arm A 官方打分物理证据（该补丁将在其中实际承压）+ Owner review |
| journal/quarantine/timeout/gpu_lock | 本仓库（harness） | 已修+测试 | 无需上游 |
| close() 显存行为 | multimodal-art-projection/YuE | 保持观察记录（G3 BLOCKED 依据） | Gate D 物理调查后随上游对话提交 |
| AR Hang / HIP fault | sgl-project/sglang#42106 / PyTorch-ROCm（归属待证） | 未动（需 GPU 复现） | Gate D；最小独立复现前不得指派归属 |
| 脱敏/guard/detector | 本仓库 | 本 C1 交付 | 无需上游 |
| 数值收据完整性工具 | 本仓库 | 本 C1 交付 | 无需上游 |
