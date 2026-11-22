# 03 — PR Stack 对照（#7–#16，W7900-RC3 复核）

方法：对 `mission/joint-blog-rc2` 工作树逐项验证各 PR 的关键不变量仍在位
（文件存在性 + 代码语义 grep + 相关测试绿）；远端状态以 gh 实况为准。

## 实况（2026-11-22）

#8–#16 全部 OPEN/DRAFT；#16 MERGEABLE（base=integration/joint-blog-rc）。
无合并、无关闭、无强推（本会话维持）。

## 不变量核查

| PR | 关键不变量 | 在位证据（当前树） | 裁定 |
|---|---|---|---|
| #7 | 公开证据 redaction + fail-closed guard | redact_evidence.py / public_evidence_guard.py / evidence_lyrics_detector.py 存在；guard+tier2 本会话 PASS | ✅ |
| #8 | Arm A 证据保全（journal quarantine、诚实 PER 门） | 移植测试（torn tail / last-status-wins / incomplete-tail refusal / interior-corruption fail-closed）在套件内绿 | ✅（以移植形式） |
| #9 | fresh-image 收尾（env 重建、RCA、验收） | 为 #13/#14 祖先，内容包含于栈 | ✅（吸收） |
| #10 | CPU-only 风险收尾 | 公共证据卫生 + PER 分析 + release gates 在 #15 内容中 | ✅（吸收） |
| #11 | C2 科学/溯源加固 | 同上 | ✅（吸收） |
| #12 | C2.1 fail-closed：原子发布、no-clobber、provenance 链、TOCTOU | atomic_publish.py（renameat2/link no-clobber）、verify_provenance.py、verify_numeric_receipt_integrity.py；相关测试绿 | ✅ |
| #13 | 镜像交换 resume 加固（C1–C4、恢复/评测器工具） | resume_wsb.py、evaluator_install.sh、driver_alive、evidence-gated 链 | ✅ |
| #14 | M1 运行时/生命周期（= 战役检出 fee027d） | server_identity.py、armB_acceptance.sh（每退出路径停机、receipt 定点 stop）；GPU 实测 P3/P10 | ✅ |
| #15 | 集成 RC（119 提交） | base 本身 | ✅ |
| #16 | RC2/RC3 修复叠加 | 2×P1 + P2/P3 修复 + 33 个新测试（18 RC2 + 15 RC3）；configs 对 base 零 diff | ✅ 不破坏上述任何不变量 |

## 处置建议（owner 门，不变）

沿用 RC2_01b：#8/#10/#11/#12 在 #15 合入后 close as superseded；#13/#14 折入；
#15 为 RC 候选；#16 作为最终修复层。主干合并与上游外发均需 owner 明确批准。
