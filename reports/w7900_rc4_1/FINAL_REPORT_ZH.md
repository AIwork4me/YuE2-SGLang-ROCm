# RC4.1 最终报告（Fail-Loud、真实健康、有界输入与证据收口）

日期：2026-11-22/23（UTC）。执行主机：j-7uqnwhrwmv2s44k6zdqzoq5idj
（Ubuntu，ROCm 7.2.1 host / 7.14.1 userspace，AMD Radeon PRO W7900D
48GB gfx1100 @ PCI 0000:03:00.0，51522830336 B = 47.98 GiB = 51.5 十进制 GB）。

## A. Executive Verdict

1. **GPU_EXECUTION_IDENTITY_VERDICT = PASS**（双栈 gpu_identity 收据 +
   实测计算探针 + 负向控制 rc3；RC4 疑似回退闭合为 SUSPECT_UNCONFIRMED，
   盲区已消除）
2. **SERVER_READINESS_VERDICT = PASS（项目级）**（/health=200 且调度器死亡
   → WORKER_DEAD 实证检测；上游 scheduler 缺陷 UPSTREAM_BLOCKED）
3. **LIFECYCLE_VERDICT = PASS**（run_with_server.sh 全生命周期包装器 +
   全程持锁证明 + 信号级联 + 5 项回归）
4. **INPUT_BOUNDARY_VERDICT = PASS**（repeated-tags "挂起" 根因 = 测试
   预算缺陷而非服务端缺陷；两种预算 regime 真机实证有界；输入预检契约）
5. **EVIDENCE_INTEGRITY_VERDICT = PASS**（791 行重算一致；验证器 CI 守护；
   冻结证据 15825 文件逐字节不变）
6. **RC4_1_ENGINEERING_VERDICT = GO（工程侧）**
7. 保留：PER_PARITY = BLOCKED_EXTERNAL；JOINT_PUBLICATION = NOT_PRESENT

## B. 精确 Git 状态

- 基线：`16f2504cbc6aaae92276e2bc03c83836fb78d2d2`（= PR #17 head，
  推送前 git fetch 复核无漂移）
- RC4.1 分支：`mission/w7900-rc4-1-fail-loud-health-evidence`
- 最终 HEAD / 远端 SHA / PR URL / exact-head CI URL：
  见 `05_GITHUB_HANDOFF.md`（推送后填定）
- 未改 main；未 force-push；未自动合并

## C. GPU Fail-Loud

- 疑似回退重析：原生路径无设备回退分支（device=cuda:0 固定）；KFD 无上下
  文只能排除"该窗口有 GPU 执行"，不能区分 CPU 回退 / 装载-传输停滞；
  机制 SUSPECT_UNCONFIRMED，根因盲区（无身份/执行/进度收据）已由
  gpu_identity 链关闭
- 真机：Env A/Env B GPU_EXECUTION_VERIFIED；错误 arch/BDF 均 rc3 立即失败
- 原生真生成：rc41_native_pilot 2/2 complete（596.2s/512.6s，官方协议，
  音频 191.3s/154.8s 与冻结战役逐秒一致）

## D. Worker Liveness

- /health 与 GENERATION_READY 分离：调度器 SIGKILL 后 /health=200 而
  readiness=WORKER_DEAD（真机负控）；在途请求有界（客户端 120.1s）；
  优雅停止被拒 rc3 → 操作员阶梯（自有验证 pid）→ VRAM 28,028,928 B；
  重启 READY；最终验证关停、端口释放
- Idle busy-loop：9145 ticks/90s = 101.6% 单核（RC4 101%）确定性复现；
  根因定位上游 scheduler.py event_loop 空队列无退避；复现器备妥待所有者
  授权提交；运维缓解 = 会话级服务器
- 两级健康：Level 1 进程/身份/调度器事实；Level 2 opt-in 真实短生成
  canary（B1 已直接等价实证 200/37.2s）

## E. Input & Lifecycle

- repeated-tags 根因：载荷 schema 合法 → 服务端默认全曲预算（9000/32）
  → 分钟级正常生成 vs 60s 测试超时；SHORT 预算 200/9.0s、DEFAULT 预算
  200/335.8s 双证；修复 = 矩阵预算 + input_budget 预检（冻结协议路径隔离）
- 锁作用域：所有会话单次持续持有（B1 会话内探针实证 held=true + who 匹配；
  退出释放收据）；RC4 `wait -- true` 模式退役
- 取消/恢复/关停：信号级联到被包装命令；B2 恢复阶梯全程留证；孤儿扫描清洁

## F. Evidence Reconciliation

- 实际原始行数 **791**（768 campaign_frozen + 23 rc4_fresh）；
  FINAL_REPORT_ZH 与 SUMMARY 修正（786→791、armA fresh n=2→7）并保留
  快照注释
- 缺失 CSV 分类 = A（本机存在未提交）：三个 CSV 经守卫扫描后提交
- 聚合 P95 方法漂移修正（申报线性插值，--regenerate 由原始 CSV 重算）
- 51.5 GiB 误标 → 51.5 decimal GB (= 47.98 GiB)（两处）
- 陈旧 PENDING 判定 → 终态（注明超集时间线）
- README：RC4.1 状态块、性能表（含 n/来源）、快速开始验证命令、"native
  pending" 陈旧声明清除；KNOWN_LIMITATIONS 四条新增
- 冻结证据保护：执行前后 SHA256 全量比对逐字节一致

## G. Tests & Mutations

- CI 域：**425 passed / 0 failed / 26 honest skips**（新增 56 项：
  gpu_identity 15、server_readiness 13、input_budget 13、
  lifecycle 5、evidence 13 含 live 守护）；工作区附加 +33
- 变异控制：**12/12 KILLED**（M7/M10 首轮 SURVIVED 暴露真实测试缺陷
  ——超时测试优先级 bug、行数声明检查过松——已修复后复杀；M2/M8 首轮
  NOT_RUN 系变异模式过期，已对齐真实代码）
- 真机 W7900：短生成、原生 2/2、调度器死亡检测、/health200-but-FAIL、
  repeated-tags 双 regime、全生命周期持锁、恢复阶梯、验证关停、端口与
  GPU 资源释放 —— 全部真机收据在案

## H. Independent Review

AI_INDEPENDENT_REVIEW（非人类批准）：冻结路径零 diff；开发中发现并修复
F1（exec-弃-trap）、F2（pid 文件未导出）、F3（两项变异暴露的测试缺陷）；
接受并记录 F4（多 GPU 主机 BDF 尽力而为）、F5（BUSY=0 语义）；无新增
CPU 回退面；资源释放与孤儿扫描清洁。PR #17 合入建议：#16 → #17 → RC4.1
（Owner 决策，未自动执行）。

## I. Release Gates

G1 待推送后 exact-head 确认 · G2 PASS · G3 PASS · G4 BLOCKED_EXTERNAL ·
G5 IMPROVED_PARTIAL · G6 PASS_WITH_PARTIALS · G7 PASS · G8 同机 PASS/
第三方 NOT_PRESENT · G9/G10 NOT_PRESENT。三判定分离维持。

## J. GitHub Delivery

原子提交（8 个逻辑提交：M1/M2/M3×2/M4×2/M5×2 + 报告）；推送前后检查
（diff --check / status / 证据守卫 / 全套测试）；堆叠 PR 指向
mission/w7900-rc4-repro-reliability；exact-head CI 与证据摘要在 OWN PR
发布。详见 `05_GITHUB_HANDOFF.md`。

## K. Remaining Work

1. 上游 scheduler 空转忙循环：Owner 授权后提交 02_IDLE_SPIN_REPRODUCER
   （验收 = 上游确认/修复或文档化运维缓解——后者本次已达成一半）
2. PER 跨评测器平价：授权 CUDA 主机执行已验证工具包
3. 独立第三方复现（不同执行者/机器）
4. 作者/AMD 发布批准（Owner 外联）
5. RC4 CPU 回退嫌疑机制：如复发，新契约将产出决定性收据
   （GPU_UNAVAILABLE / EXECUTION_FAILED 而非静默）

## 执行摘要（≤150 字）

RC4.1 在真实 W7900D 上交付 fail-loud GPU 身份链（双栈执行验证、错误
arch/BDF 立即失败）、真实生成就绪检查（/health=200 且调度器死亡实测判
WORKER_DEAD）、全生命周期 GPU 锁包装器（含信号级联与孤儿零残留）、
repeated-tags 根因修正（测试预算缺陷，双 regime 真机实证非挂起）与 791
行证据重算收口（冻结证据逐字节不变）。425 项测试与 12/12 变异全杀；
PER 平价与联合发布仍开放，上游缺陷如实标注 UPSTREAM_BLOCKED。
