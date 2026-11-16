# 镜像更换交接手册（IMAGE_SWAP_HANDOFF）— 2026-11-16T12:45Z

**触发**：Owner决定更换镜像。Arm A已**优雅停止**于 **177/384 verified，0 failed**
（SIGINT→in-flight候选#177完成→驱动自然退出，journal一致，"stopped by signal;
state is resume-safe"）。全部CPU工程已冻结（PR #7 merged；#10 `8756125`；#11
`4d9f4a2`；#12 `d66ffbf`，CI全绿）。

## 1. 可下载归档（唯一不可快速重建的资产=177个已生成音频bundle）

| 项 | 值 |
|---|---|
| 路径 | `/workspace/armA_state_20261116T1145Z.tar.gz`（同份留存 `/data/yue2-runs/`） |
| 大小 | 7.2 GiB |
| **SHA256** | `45e7c0f9a443cdbd4e822536214155c9c3905da611e55a04c15cf98fe4c32da7` |
| 内容 | `armA_wsb_full/songs/`（177个完整bundle：audio.flac+result/request/config.json+semantic/latent/prefix.npy）· `generation_manifest.jsonl`(177 complete) · `run_config.json`(+pre_migration备份) · `evaluation_inputs.jsonl` · `_gen_worker.py` · `_handoff_logs/`（驱动日志+mission_chain日志） |
| 排除 | `.partial`（无残留：停止时为0） |

下载校验：`sha256sum -c armA_state_20261116T1145Z.tar.gz.sha256`
若下载通道限大小：`split -b 2G armA_state_….tar.gz part_`（新镜像端 `cat part_* > …` 后同法校验）。

## 2. 新镜像后的上传位置设计（推荐→备选）

**版权约束**：音频含WildSongBench授权歌词的模型演唱（研究用途）——**禁止公开
GitHub**（公开仓库红线）。必须放**受限私有存储**。

### 推荐：Hugging Face 私有数据集仓
```bash
# 新镜像上（或任何机器）：
pip install -U "huggingface_hub[cli]"
hf auth login                      # 用你的HF token（需dataset写权限）
hf repo create yue2-armA-audio-restricted --type dataset --private
hf upload AIwork4me/yue2-armA-audio-restricted armA_state_20261116T1145Z.tar.gz . --repo-type dataset
hf upload AIwork4me/yue2-armA-audio-restricted armA_state_20261116T1145Z.tar.gz.sha256 . --repo-type dataset
# 目标镜像上取回：
hf download AIwork4me/yue2-armA-audio-restricted armA_state_20261116T1145Z.tar.gz --repo-type dataset --local-dir /data/yue2-runs/
sha256sum -c armA_state_20261116T1145Z.tar.gz.sha256   # 必须与上方哈希一致
```
私有仓+访问控制即本mission一贯的"受限原件存储"（LQ-1 Option A同语义）。

### 备选（任选其一，校验流程相同）
- 实验室对象存储/S3：`aws s3 cp … s3://<your-private-bucket>/`（私有桶+加密）
- rclone 到任意私有网盘（`rclone copy … remote:restricted/`）

## 3. 新镜像恢复与续跑流程（逐步、含门禁）

```bash
# (1) 重建仓库与分支（含全部CPU工程）
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git
cd YuE2-SGLang-ROCm && git checkout mission/w7900-fresh-image-final-closure
# CPU工程栈（可选启用）：PR #12链 fix/c2-1-final-fail-closed-closure（含溯源驱动）

# (2) 重建工作区（既有配方，~1-2h）
python3 scripts/check_environment.py
export YUE2_WORKSPACE=/data/yue2 && mkdir -p $YUE2_WORKSPACE/{logs,tmp,hf-cache} /data/yue2-runs /data/tmp
python3 scripts/download_pins.py --workspace $YUE2_WORKSPACE          # 全pin哈希校验
bash scripts/campaign_ops/build_envA.sh                              # Env A（torch 2.10.0+rocm7.1）
bash scripts/campaign_ops/evaluator_install.sh                       # Env C（评估器+AMD替换）
# Env B（Arm B阶段前再做）：campaign_ops/build_envB.sh

# (3) 恢复campaign状态（先校验！）
cd /data/yue2-runs && sha256sum -c armA_state_….tar.gz.sha256        # 不符=传输损坏，禁用
tar xzf armA_state_20261116T1145Z.tar.gz                             # → armA_wsb_full/ + _handoff_logs/
# 门禁：恢复后审计（应=177 verified，PILOT语义）
YUE2_WORKSPACE=/data/yue2 $YUE2_WORKSPACE/environments/yue2-torch/bin/python \
  scripts/verify_wsb_artifacts.py --runs /data/yue2-runs/armA_wsb_full --mode pilot --expect 354
# 注：manifest恢复后177个候选都应verify_result通过；--expect 354=全部384对（缺失207在journal中
# 无complete记录→audit按pilot子集语义核验已有bundle；两倍校验以实际脚本输出为准，
# 任何"journal complete但verify失败"=恢复损坏→停止排查

# (4) 续跑（resume安全；驱动可为PR#12链新代码——稳定身份一致：driver_protocol=armA-driver/1）
bash scripts/campaign_ops/run_armA_campaign.sh   # 期望日志 already_complete=177，继续生成#178…
nohup setsid python3 scripts/campaign_ops/mission_chain.py > /data/yue2/logs/mission_chain.log 2>&1 &
# 完成后自动：审计FULL→PER+SongBench→MuLan/AMC→Arm B（campaign_ops/内有全部脚本）

# (5) GPU单租户纪律不变：gpu_lock自动生效；勿并发评测
```

## 4. 状态快照（入git，见 evidence/publication/fresh_image/armA/）

- `generation_manifest_snapshot_20261116T1145Z.jsonl`：177 complete 记录
- `progress_20261116T1145Z.json`：含归档SHA256与本手册指针
- `scripts/campaign_ops/`：全部会话运维脚本入库（mission_chain/launcher/watchdog/
  环境构建/资产重试器）

## 5. 遗留待办（镜像无关）

Owner：PR #12→#11→#10整合 · PR #8关闭 · LQ-1历史处置 · 上游0010（等打分）
物理侧：剩余207候选(~41h GPU)→审计→四指标→Arm B→PER对照→AR Hang→HIP→G20
