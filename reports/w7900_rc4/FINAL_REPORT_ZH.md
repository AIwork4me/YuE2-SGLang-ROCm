# W7900-RC4 最终报告（可复现性、运行时可靠性、性能与发布加固）

日期：2026-11-22（UTC）。执行主机：j-7uqnwhrwmv2s44k6zdqzoq5idj（Ubuntu 24.04，
ROCm 7.2.1 / HIP 1.18，AMD Radeon PRO W7900D 48GB，gfx1100）。

## A. 执行判定（Executive Verdict）

1. **FRESH_CLONE_REPRODUCIBILITY_VERDICT = CLEAN_CLONE_SAME_HOST_PASS**
   （同一主机全新克隆复现成功；非独立第三方复现，未冒充 G8 全量通过）
2. **RUNTIME_RELIABILITY_VERDICT = PARTIAL**
   （R1 空转忙循环已确定性复现并定性；历史 ~1/300 请求内挂起未复现、未声称修复；
   生命周期保证在真实硬件上全部验证通过；R2 并发边界保留未压测）
3. **PERFORMANCE_VALIDATION_VERDICT = PASS_WITH_PARTIALS**
   （分布证据 n=384/臂（冻结活动收据）+ 新鲜漂移校验 + 冷启动/并发/资源边界实测；
   每臂新鲜样本 n<30，如实标注 PARTIAL）
4. **RC4_ENGINEERING_VERDICT = GO（工程侧）**
   （8 个缺陷发现、6 个修复带回归测试、2 个记录为后续项；冻结证据零改动并复验哈希；
   CI 域 367/0 本地通过；远端 exact-HEAD CI 见交付节）
5. 保留判定：**PER_PARITY = BLOCKED_EXTERNAL**（需授权 CUDA 主机）；
   **JOINT_PUBLICATION = NOT_PRESENT**（无作者/AMD 批准，未作任何暗示）

## B. 精确 Git 状态

- 起始 SHA：`48d1cb64fa2b4653ee40606a8dfbe3593c5b0b6f`（实时核验 = 线上 PR #16 head，无漂移）
- RC4 分支：`mission/w7900-rc4-repro-reliability`（基于上述 SHA）
- 本地最终 SHA / 远端 SHA / PR URL / CI URL：见 `05_GITHUB_HANDOFF.md`（推送后填定）
- 未改 main；未动 PR #15/#16；未 force-push

## C. 全新克隆复现（M1）

实际执行（收据齐全，`01_COMMAND_RECEIPTS.jsonl`）：固定提交克隆 → 环境诊断 PASS →
全部 pin SHA256 校验 PASS（Mode A 缓存拷贝全部过哈希门；Mode B 部分全新下载：
代码/两套 venv/评测器树重建/数据集元数据，大权重为哈希等价缓存拷贝——如实记 PARTIAL）。

- **原生 PyTorch 路径**：2/2 完整歌曲（694.9s/620.5s；音频 191.3s/154.8s；官方种子；
  工件齐全），中断→隔离→续跑验证通过；审计 PILOT 0 问题
- **SGLang 路径**：2/2 完整歌曲（总 635.5s，峰值 VRAM 47.1GiB），身份验证关停 rc=0，
  VRAM 完全释放
- **试点审计/评分**：两臂 `--mode pilot` 均 PILOT 0 问题；官方冻结评测器 shard 模式
  评分四指标全部 complete=true（Arm A 试点 PER micro 12.93%/Arm B 8.60%；MuLan 均值
  A 0.4345/B 0.4660；AMC A 0.4550/B 0.4765；SongBench 每候选收据齐全，
  如 Arm A wsb_000_r0 Global Avg 6.93——2 候选试点值，明确不可与 192-prompt 聚合比较）
- **复现过程中发现并修复 7 个缺陷**（冒烟脚本陈旧 venv 路径、宿主 python 终化浪费
  GPU 工作、审计器隔离目录误报、伪造收据崩溃、资产工具硬编码路径、独立选择键不忠实、
  QUICKSTART 四处文档缺口）——每个都有"复现→修复→重跑→收据"链
- 负向控制 NC1–NC10 全部 fail-closed（2 个产生修复）

## D. W7900 运行时可靠性（M2）

执行量：62 短请求 + 20 完整歌曲 + 1 长歌词 + 1 超大输入 + 10 非法请求 + 3 次真实
中断续跑 + 2 次调度器 SIGKILL + 5 次服务器（重）启动 + 锁竞争 + 孤儿扫描。

- **R1 空转忙循环（确定性复现）**：干净完成 1 个短请求后空闲 90s 采样 =
  **单核 101%**（GPU 0%）——`sgl_diffusion::scheduler` 空闲期持续忙轮询；
  会话开始时捕获的孤儿服务器同一签名持续 8.7 小时（22.7GiB VRAM 滞留、/health 正常）
- **健康端点盲区（故障注入实证）**：调度器被 SIGKILL 后，在途请求挂起至客户端超时
  （curl rc=28），/health 仍 200，worker 不重启；SIGINT 关停可卡在"等待后台任务"，
  身份工具正确拒绝（rc=3），恢复阶梯 SIGTERM→SIGKILL 全程留证
- **输入边界**：~2.6KB 重复 tags 载荷使请求路径挂起 >60s（缺陷候选，2/2 复现）；
  2MB 载荷 1.4s 干净 500；40 段歌词 1123s 有界完成
- **R3 内存生命周期（5 循环）**：close() 释放 torch 分配 346→80MB；GC 释放 ~1.4GB
  RSS；基线跨循环不增长——**有界残留，非泄漏**（RC1 未决项收窄关闭）
- 修复：审计器隔离语义、终化解释器自动选择、收据字段校验等（见 05 独立评审）
- 遗留：R1 上游根因（容器禁 ptrace，无法取 Python 栈）；请求内 ~1/300 挂起未复现
  （样本量不足以做任何统计声称）；R2 并发压测未执行（边界保留）；原生管线在外部
  GPU 租户压力下出现一次**静默 CPU 回退**嫌疑（worker 无 KFD 上下文、191% CPU、
  46 分钟零 GPU；替换 worker 立即恢复 GPU 99%）——证据已存，需上游 fail-loud 修复

## E. 性能（M3，冻结方法学）

原始数据 786 行（`03_PERFORMANCE_RAW.csv`），主速度指标 =
audio_seconds / generation_wall_seconds（音频实时倍率；常规 RTF 为其倒数，分开标注）。

| 路径 | 证据 | n | P50 | P95 | 音频倍率均值 | 峰值 VRAM |
|---|---|---|---|---|---|---|
| SGLang 服务 | 冻结活动 n=384 + 新鲜 16 | 384/16 | 275.3s / 248.3s | 429.6s | 0.791 | 活动 51.5GiB(=卡上限)/试点 47.1GiB |
| 原生 torch-eager | 冻结活动 n=384 + 新鲜 7 | 384/7 | 706.4s / 630.4s | 1033.1s | 0.309 | GPU 分配 ~0.35GiB（24GiB 预算流式） |

- 冷启动：服务器进程→health = **30s**（4 次一致）；首请求惩罚 +50–120s（2 样本）；
  原生管线冷加载 ~2–3 min
- 并发：C=2/4 客户端并发=纯排队（服务端 batch=1，阶梯时延实测）；C=8 未重跑
  （RC2 证据已覆盖，如实标注）
- 吞吐：Arm B 活动 12.2 首/小时；Arm A ~5 首/小时
- 同卡对比：SGLang P50 快 ~2.6×（同权重同参数，配置差异披露）；无跨厂商声称

## F. 科学证据复核（M4）

- **Prompt-19 平局**：官方冻结键为四元组（per, edits, |音素长度差|, candidate_index）；
  r1 以第三分量 3<11 合法胜出——**官方实现完全确定，无欠规范**；独立复算脚本键
  不忠实（2 处缺陷）→ 已修复 + 5 个回归测试（含冻结 192/192 身份核验与变异控制）
- **5 个截断但完整候选**：Arm B 全部为 ABC 段 4096 上限（语义段自然结束）；
  Arm A 修正计数同为 5（3 语义上限、3 ABC 上限、1 双重）；prompt 113/164 双后端
  皆截断（长歌词驱动，非后端缺陷）；与 ASR_CAPPED 严格区分；冻结 audit.json 的
  384 为修复前陈旧值（已文档化，未改动）
- **来源分级**：384 LEGACY 如实标注未升级；新运行 run_config 增加 driver_repo_head；
  35/35 回归测试保证缺源身份永不通过为 FULL
- **历史结果分离**：README/EVIDENCE_INDEX 重构为"当前代（RC2-RC4）"与"历史"两张表，
  以 run_id 键控，永不混算

## G. 独立工程评审（M5.1）

8 个缺陷（P0×2、P1×4、P2×2）：6 个修复（冒烟 venv、终化解释器、审计器隔离、
收据校验、资产工具隔离、选择键），全部带正/负测试与真实硬件重验；2 个记录为
后续项（试点带服务器生命周期包装器、上游 R1 复现器草稿——未经所有者授权不外发）。
自我披露：本任务窗口脚本的锁范围缺陷（`wait -- true` 即释放）——物理单租户全程
成立，但锁纪律弱于规则，已记录。

## H. 发布门 G1–G10

G1 CONDITIONAL-PASS（远端 exact-HEAD CI 推送后确认）· G2 PASS · G3 PASS ·
G4 BLOCKED_EXTERNAL · G5 PARTIAL（实质改善：根因类别已定性）·
G6 PASS_WITH_PARTIALS · G7 PASS（工作树；历史 git 对象仍属所有者/法务）·
G8 PASS(同主机)/NOT_PRESENT(第三方) · G9 NOT_PRESENT · G10 NOT_PRESENT。
三判定分离：ENGINEERING_GO ✓、SCIENTIFIC_PARITY_GO ✗、JOINT_PUBLICATION_GO ✗。

## I. GitHub 交付

分支 `mission/w7900-rc4-repro-reliability`；原子提交；推送前后检查
（diff --check / status / 证据扫描）完成；堆叠 PR 指向 `mission/joint-blog-rc2`。
提交/PR/CI URL 与最终证据清单：`05_GITHUB_HANDOFF.md`。

## J. 遗留工作（仅基于证据的未决项）

1. **R1 上游根因**：调度器空闲忙循环的最小复现器 + 上游 issue（所有者授权后提交）；
   验收=上游确认/修复或本仓库文档化的运维缓解（空闲即停服）
2. **试点带服务器生命周期的仓库级包装器**（R1-L1 的彻底关闭）；验收=中断路径
   自动身份验证关停 + 测试
3. **重复 tags 输入挂起**（缺陷候选）：最小化载荷 + 修复或上游报告；验收=有界拒绝
4. **PER 跨评测器平价（G4）**：授权 CUDA 主机执行已验证工具包；验收=A2/B2/C1/C2
   决定性单元格完成
5. **独立第三方复现（G8 外部项）**：不同执行者/机器按 QUICKSTART 走完全程；
   验收=外部执行者签署的偏差记录
6. **作者/AMD 发布批准（G9/G10）**：所有者外联；验收=书面批准

## 执行摘要（≤150 字）

RC4 在真实 W7900D 上完成全新克隆端到端复现（双路径出完整歌曲、试点审计与官方
评分、10 项负向控制），确定性复现 SGLang 调度器空闲忙循环并实证健康端点盲区；
产出 786 行性能原始收据（P50：SGLang 275s vs 原生 706s，冷启动 30s，并发纯排队）。
解决 prompt-19 选择平局（官方键确定，独立键缺陷已修），冻结证据零改动并复验。
6 缺陷修复带回归，367/0 本地 CI，工程 GO；PER 平价与联合发布仍开放。
