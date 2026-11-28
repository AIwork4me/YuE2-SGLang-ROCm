# MISSION RC6 — 最终报告（中文）

时间线：2026-11-27 全天（接手 RC5.1 完成态 `57e81c2`，实时复核后连续执行）。
所有结论可回溯至 `reports/developer_reference/` 下的机器可读回执；本文件是入口。

---

## A. Executive Verdict

| 阶段 | 判定 |
|---|---|
| RC5.2 科学证据闭合 | **PASS**（唯一开放项：H10 内核级环触发，已有界计划；官方 CUDA 对照外阻塞） |
| RC5.2 开发者黄金路径 | **PASS**（CLI、quickstart、验证工具、首歌 FULL_SONG_PASS、6 项摩擦全部修复复验） |
| RC5.3A 作者验收准备 | **READY（未提交）**——A01–A12 矩阵、CUDA runbook、比较器、请求草稿齐备 |
| RC5.3B 同机复现（Mode 2） | **PASS**（新检出 + 新 venv + 新 workspace，运行时身份逐位一致，同种子首歌字节一致） |
| RC5.3B 独立第三方复现 | **NOT_RUN**（无独立主机/执行人；交接包就绪，不冒充） |
| RC5.4 上游整合准备 | **READY**（19 个 PR 拓扑实时审计；补丁按问题归属；整合计划含合并时守卫门） |
| RC5.4 AMD 工程验收 | **包就绪未提交**（AMD01–AMD10；无任何 AMD 人员参与，不自称批准） |
| Release Candidate | **v1.0-rc1 已准备未发布**（精确 HEAD CI 见 PR 回执） |

外部门禁（如实）：异机备份 BLOCKED_EXTERNAL；官方 CUDA PER/Q3O 对照
BLOCKED_EXTERNAL；作者认可、AMD 批准、第三方复现 —— 均不存在也未声称存在。

## B. Developer Value（开发者现在怎么用）

```bash
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git && cd YuE2-SGLang-ROCm
python3 scripts/reference_cli.py doctor        # 环境诊断（GPU 检查 fail-loud）
python3 scripts/reference_cli.py install       # 锁定栈：torch 2.12.0+rocm7.14.1 + sglang c67d541a + 导入守卫
python3 scripts/reference_cli.py generate --lyrics examples/first_song/lyrics_en.txt \
  --style examples/first_song/style.txt --seed 831001 --out-dir $WS/runs/my-first-song
python3 scripts/reference_cli.py verify --run-dir $WS/runs/my-first-song   # 六级判定词
python3 scripts/reference_cli.py benchmark --mode pilot|full               # 分层基准
python3 scripts/reference_cli.py status|resume|stop|compare|package-evidence
```

失败可诊断（docs/TROUBLESHOOTING.md 十二类失败模式：症状→诊断→原因→处置→恢复→升级），
评测身份可审计（ASR_RUN_IDENTITY 合同 + fail-closed resume），结果可自证
（判定词含 VERIFIED_REFERENCE_RUN，分数接近永不单独授信）。

## C. Exact Git State

- Initial HEAD（接手）：`57e81c2ccb664a4a5eedf9a9526d0709647ba9aa`（PR #19 HEAD，实时核验 OPEN/DRAFT、双 job CI 全绿）
- Final HEAD：见 PR（RC6 分支 `mission/rc6-developer-reproduction-reference`，8 个原子提交，无 force-push、未动 main、未合并/关闭任何 PR）
- PR：https://github.com/AIwork4me/YuE2-SGLang-ROCm/pull/20（[RC6] Developer Reproduction Reference）
- Exact-HEAD CI：PR 回执记录最终 SHA 的 push+PR 双运行 run id（cpu / q3o-moe-cpu-numerics）

## D. RC5.2 结果

- **确定性**：380/384 字节一致（现场重推导）；4 个差异件通过无损自洽
  （解码 PCM MD5 == STREAMINFO MD5）、同构建重编码字节一致；ffmpeg 异编码
  对照证明"同 PCM 异字节"（编码器构建敏感性机制实证）；历史 FLAC 缺失 →
  `PCM_IDENTITY_UNVERIFIABLE_HISTORICAL_ARTIFACT_ABSENT`，内容一致性
  NOT_ESTABLISHED（不伪造）。新增：跨 workspace 同种子字节一致。
- **评测者身份**：ASR_RUN_IDENTITY 合同（模型文件哈希/引擎/预处理源/解码参数/
  manifest/驱动）；resume 由"只按 id 跳过"改为 fail-closed（REJECT 分类 +
  尾部隔离 + supersede）；scorer 去 assert 化 + 重复/覆盖/重复数/混臂/
  分母审计；官方 PER 数学不动（GREEN 回归逐字段一致）；两历史臂只读审计
  0 违规。20 离线负向控制 + 1 现场 resume 控制全过。
- **PER 归因（2×2，同一批 384 音频）**：T(S_T) 17.7699% / V(S_T) 9.5854% /
  T(S_V) 20.2042% / V(S_V) 8.4488%；分解：引擎路径 −8.18pp（主导）、选样
  −1.14pp；60/120 之惑以四显式字段解决（60 变更 prompt = 120 对称差）。
- **修正记分板（Scoreboard B）**：冻结官方评测器在 S_V 上实跑 192/192：
  SongBench 6.742109 · MuLan 0.504299 · AMC 0.403000 · PER 8.4488%；
  与 A 分列发布，绝不混算；Q3O-on-S_V 未跑（预算披露）。
- **黄金路径**：见 B 节 + `05_*` 五件套。

## E. RC5.3A 结果

作者包（英文、一页执行摘要、A01–A12 矩阵、证据链接、复现命令、补丁、
局限、请求决策四项）；CUDA PER/Q3O runbook（预注册判据规则：先定容差后跑）；
比较器自测两次通过；请求草稿未发送（需 Owner 授权）。修正历史"author-verified
commands"表述为"commands executed on our W7900 rig"。

## F. RC5.3B 结果

Mode 2（同机全新检出/venv/workspace，如实标注，不冒充 3/4）：doctor PASS、
pins 哈希一致、运行时身份 342b2f53… 逐位一致、首歌生成+验证
VERIFIED_REFERENCE_RUN、同种子 FLAC 与主 workspace 字节一致、6 项摩擦
（含 CLI 安装缺上游检出、代理慢克隆、finalize 环境、验证工具字段路径）
全部根因+修复+复验。R01–R20 矩阵 + 独立执行人交接包（含回执 schema）。
R09–R12 新工作区未跑（GPU 预算，如实披露）。

## G. RC5.4 结果

PR 拓扑（19 个实时审计）：开放栈线性且全部包含于 #19；#8 三个侧分支提交
未 cherry-pick（patch-id 证实），功能被 main #7 + C2/C2.1 + RC5.1 取代，
Owner 决策已记录；合并时双守卫套件门（main #7 与链条守卫独立演化）。
补丁归属（A/B/C 三类、逐问题最小复现器与移除条件）。AMD 包（十项矩阵）
未提交。许可与安全：守卫全过、无密钥、原创歌词可发布、历史 Git 对象
未扫描（披露 + 合并时门）。RC v1.0-rc1 三件套 + 公共声明矩阵。

## H. Performance & Quality

性能包络（重算）：冷启动≈46s；P50 275.27 / mean 284.78 / P95 434.33 /
P99 496.62 s；AR 164.2 / NAR 42.2 / VAE 78.4 s；RTF 1.2866；实时倍率 0.7894；
顺序吞吐 12.64 首/h；生成峰值 VRAM 29.7 GiB（卡总量口径）；Q3O 峰值
42.41 GiB（torch 口径）+ 宿主 VmHWM 49.83/55 GiB。单位纪律 GiB=2³⁰，
三种内存口径分列。

科学记分板（分臂，绝不拼接）：

| 臂 | SongBench | PER | MuLan | AMC | Q3O |
|---|---|---|---|---|---|
| 论文/官方 CUDA | 6.7316 | 8.44% | 0.5068 | 0.4054 | 4.68 |
| A：冻结 transformers 臂（S_T） | 6.736891 | 17.7699% | 0.509395 | 0.405181 | 4.393986（ROCm 适配） |
| B：修正 vLLM 臂（S_V，RC6 实跑） | 6.742109 | 8.4488% | 0.504299 | 0.403000 | 未跑（披露） |
| C：官方 CUDA 同音频对照 | 未跑（BLOCKED_EXTERNAL） | | | | |

## I. Regression & Negative Controls

CPU 套件 585 通过 / 3 诚实 SKIP / 0 失败（生成 venv；CI 排除集与硬件集
分工不变）；compileall / bash -n / diff-check / 证据守卫 / 数字回执 /
密钥扫描全过。GPU 现场：首歌（两 workspace）、pilot 1x2（VALID_PILOT_ONLY）、
Q3O smoke（身份回执）+ 比较器扰动检出、错误架构负向（exit 3）、死 worker
readiness、陈旧锁接管、ASR live resume（复用仅限身份精确匹配）。变异控制：
Q3O 15/16 冻结结果 + G2 分类复核（EXPERIMENTAL_NOT_DEFAULT，零影响已发布数值）；
ASR 回执内容变异改变回执哈希。

## J. Frozen Evidence Integrity

任务前后 13,859 文件 / 81.5 GB SHA256 全量复核：**0 失配、0 多余文件**
（含 384 音频、两臂回执、Q3O 回执、备份卷、恢复演练镜像）。

## K. Release Gate Ledger（G00–G28 摘要）

20 PASS · 3 BLOCKED_EXTERNAL/NOT_ESTABLISHED（G12/G14 官方 CUDA 对照、
Q3O 等价）· 5 NOT_RUN（G19–G21 第三方、G25–G27 作者/AMD 批准）·
G01 由推送后精确 HEAD CI 回执闭合。逐门禁证据与行动：
`FINAL_RELEASE_GATE_LEDGER.json`。

## L. GitHub Delivery

分支 `mission/rc6-developer-reproduction-reference`（自 57e81c2，8 个原子
提交）；PR #20（Draft→按实际状态选择）；PR 正文含执行摘要/开发者价值/
精确栈/前后对比/科学修正/完整记分板/性能/新鲜克隆/独立复现状态/作者与
AMD 状态/上游状态/遗留阻塞/审阅决策/证据索引（链接到文件，不粘贴长文）。

## M. Remaining Actions（仅真实未完成项）

1. **官方 CUDA 同音频对照（G12/G14）** — Owner：提供 CUDA 主机执行 runbook；
   验收证据：预注册判据下的对比 JSON。阻塞联合验证，不阻塞开发者发布。
2. **异机备份（G23 部分）** — Owner：授权目标；证据：异机哈希回执。不阻塞发布。
3. **作者验收（G25）** — Owner：授权提交作者包；证据：作者明确回复。阻塞联合验证。
4. **AMD 工程/发布验收（G26/G27）** — Owner/AMD；阻塞联合发布。
5. **第三方复现（G19–G21）** — 社区/Owner 提供主机与执行人；阻塞独立复现声明。
6. **H10（可选）** — 2–4 候选双引擎逐层 logits 追踪（预算 2–4 h GPU）。
7. **正式发布** — Owner 决策（GitHub Release/tag 授权）。

## N. Executive Summary

> **150 字**：RC6 在 W7900D 上完成 YuE2-on-ROCm 开发者复现参考：科学证据
> 闭合（380/384 字节一致 + 4 件 PCM 不可证如实申报；PER 2×2 归因，引擎路径
> −8.18pp 为主导；修正选样记分板以官方评测器实跑 192/192：PER 8.4488% vs
> 论文 8.44%；Q3O 边界明确不申报等价）；开发者黄金路径成型（一条命令安装/
> 生成/验证，六级判定词）；同机全新克隆复现运行时身份与同种子音频逐位一致；
> 384 音频及全部冻结证据零失配。作者与 AMD 包就绪未提交，CUDA 对照、异机
> 备份、第三方复现为外部阻塞。Release Candidate v1.0-rc1 已备未发布。

> **150 words**: RC6 delivers the YuE2-on-ROCm Developer Reproduction
> Reference on a W7900D: scientific closure (380/384 byte-identical with the
> 4 divergent FLACs honestly unprovable at PCM level; the PER gap fully
> attributed via a 2×2 same-audio matrix — engine path −8.18 pp dominant;
> the corrected selection re-scored with the frozen official evaluator,
> PER 8.4488% vs paper 8.44%; Q3O boundary explicit, equivalence never
> claimed); a golden developer path (one-command doctor/install/generate/
> verify with a six-level verdict vocabulary); and a same-host fresh-clone
> reproduction reproducing the exact runtime identity and a byte-identical
> same-seed song. All 13,859 frozen evidence files verified intact. Author
> and AMD packages are prepared but unsubmitted; CUDA comparisons, off-site
> backup and third-party reproduction remain external blockers. Release
> Candidate v1.0-rc1 prepared, not published.
