# 03 — 受控物理回归（W7900-RC3，真实 GPU 执行记录）

执行窗口：2026-11-22 03:40–05:00Z（Arm B 已终结、lock 释放、GPU 空闲之后）。
执行树：`mission/joint-blog-rc2`（PR #16 工程分支）。证据目录：
/data/yue2/logs/rc3_acceptance/、/data/yue2/logs/rc3_pilot/、/data/yue2-runs/rc3_pilot_resume/。
未触碰任何冻结战役证据（独立日志/运行目录）。

| # | 项目 | 方法 | 结果 |
|---|---|---|---|
| P1 | GPU smoke | phase0_gpu_smoke.py | **PASS**：W7900D/gfx1100，fp32/fp16/bf16 matmul 有限性 OK |
| P2 | yue2 栈导入 | env B python 导入 sglang yue2 模型/VAE/pipeline | **PASS**（torch 2.12.0+rocm7.14.1） |
| P3 | 完整官方 acceptance 流 | scripts/campaign_ops/armB_acceptance.sh（gpu_lock 全程持有） | **ARMB_ACCEPTANCE_PASS**：健康轮询有界、身份 receipt capture+verify、/v1/models 钉住模型、真实生成 33.079 s @48 kHz **rms=0.1486（非静音）** wall=91.2 s、优雅停机（SIGINT→gone）、lock 释放 |
| P4 | 确定性抽样 | P3 生成 sha256 与战役期 acceptance 对比 | **逐位一致**（7e56986b…）——同种子跨会话确定性 |
| P5 | SIGINT 优雅中断 | run_wsb.py 驱动 1 候选进行中 SIGINT | in-flight 候选完成后退出；journal 精确 `complete`；summary complete=1 pending=1 stopped_by_signal=true |
| P6 | SIGKILL 撕裂态 | 候选生成中 kill -9 | 部分目录（无 audio.flac/result.json）留存，journal 无该行 |
| P7 | 恢复 | 重启 driver 同 run_id | 跳过已完成候选（resumed 行）；撕裂目录 **quarantined(partial)**；重生成后精确 `complete`；2/2 唯一 complete（前缀去重计数）；audit `--mode pilot` **PILOT 0 problems** |
| P8 | 同种子重生成一致性 | pilot r0 与 Arm B 战役同 ID 候选 | identity `570c5ce9…` 与 audio_seconds `185.8787` **逐位一致** |
| P9 | lock 语义 | acceptance 流 acquire/release + 手动 status | 无竞争、无残留持有者；released_at 记录正确 |
| P10 | 孤儿/资源释放 | 每阶段后 ps/ss/rocm-smi | 端口 31000 释放、无存活 sglang、VRAM 归零（仅 2 个 11 月历史 defunct，无 GPU 占用） |
| P11 | 有界评测器失败 / 失败证据保全 | CPU 套件故障注入（test_mission_chain_gates 等） | 绿（超时降级、partial 移出保全、重试上界、blocked_reason） |

历史三项（AR 挂起 ~1/300、HIP IMA、close() 内存行为）：本窗口未复现亦未注入
（战役后首轮谨慎窗口）；维持 04 报告的预注册协议与历史证据，**不做根因已解决的声明**。
