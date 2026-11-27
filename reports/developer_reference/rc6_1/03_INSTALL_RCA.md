# M3 — Pinned Installation & Physical GPU Ownership (RCA)

证据：`tests/test_rc61_install.py`（11 项，含 A18/A19/A20 与 CLI 契约）、`03_PINNED_INSTALLATION_TESTS.json`（真实 workspace 两次幂等 replay）、`03_CROSS_WORKSPACE_CONTENTION.json`（双 workspace 真实锁竞争 + 真实 GPU 计算）。

## 3.1 安装 pin 漂移（cmd_install）

**缺陷（RC6）**：初始 clone 用移动分支 `add_yue2`；已存在目录时仅在 HEAD ≠ frozen 时 checkout；无 fetch/commit 存在性验证；patch 步骤无条件 `git apply`——重复安装必然非幂等地失败（RC6 代码路径里 `git apply` 已应用补丁返回非零 → EXIT_FATAL）。

**修复（`ensure_frozen_upstream()`，可测函数）**：
1. clone 仅作传输；随后 `git fetch`（失败且 frozen 本地存在 → 披露并继续；内容寻址对象本地可验证）；
2. `cat-file -t` 验证 frozen commit 存在，**不存在 → FATAL，绝不回退分支头**；
3. HEAD ≠ frozen 且树脏 → **REJECT**（绝不 `reset --hard`，用户修改保全）；树净 → checkout frozen；
4. HEAD 复验 == frozen；
5. patch 状态：reverse-check 通过 → 已应用 → 跳过（幂等）；forward-check 通过 → 应用；两者皆否 → REJECT（部分应用/分歧树）。

**RED→GREEN**：合成 git 远端测试 8 项安装路径 + 3 项 CLI 契约全部通过；真实 workspace replay×2（43s each）：frozen head 验证、patch 幂等跳过、无重 clone、runtime manifest 复写、`yue2_runtime_sha256 == 342b2f53…`（pinned 匹配）。

**CLI 解释器缺陷（实测发现并修复）**：`download`/install 的 `download_pins.py` 需 `huggingface_hub`，系统 python 无该包 → 步骤失败。修复：步骤 2/5 与 `reference download` 使用 generation venv 解释器（venv 未建时明确提示）。这是 M3.4「Correct venv interpreter」的实测闭环。

## 3.5 物理 GPU 锁域

**缺陷（RC6）**：默认锁 = `<workspace>/gpu.lock`——同一物理 GPU 上不同 workspace 各持独立锁文件，互斥失效。

**修复（`gpu_lock.py`）**：
- `resolve_physical_gpu()`：闭合物理链（恰好一个 amdgpu render node 暴露 → sysfs PCI BDF + unique_id；歧义返回 None）；**以 BDF 而非逻辑 HIP ordinal 命名锁域**（ordinal 随进程/容器变化）。
- 解析顺序：`YUE2_GPU_LOCK`（显式文件，兼容）→ `YUE2_GPU_LOCK_ROOT`（显式共享根）→ 默认 `/var/lock/yue2-gpu/gpu-<BDF>.lock`（可写且 GPU 可解析）→ **legacy workspace 回退**（GPU-less CI/只读宿主；receipt 与文档披露该模式不受跨 workspace 协议保护，不假设保护）。
- 锁 receipt 记录 `lock_domain`（name/physical/shared/legacy）与 `workspace`（环境变量级绑定，用于 stop 成员判定；cmdline 判定保留为 legacy 回退）。

**实测**（`scripts/rc61_gpu_contention.py`，两 workspace 真物理 GPU）：
1. A 持锁 → B 获取 → `LOCK_CONTENTION`（TimeoutError，B 未启动任何 GPU 负载）；
2. B 请求 stop → **REFUSED**（holder 不属于 B 的 workspace）；
3. A 安全停止（仅对记录的 holder pid 发 SIGINT/SIGTERM，无 pkill -f，无 SIGKILL）→ 域释放；
4. B 获锁并运行**真实 GPU 计算**（torch bf16 matmul on gfx1100, W7900D）；
5. 陈旧 receipt（死 pid）→ flock 为权威 → 重获；
6. BLOCKED marker → 域内拒绝获取，`unblock --yes` 清除且证据保留；
7. 不可写共享根 → legacy 回退 + 披露。

**多 GPU 宿主披露**：本机 8 个 amdgpu 函数，本容器仅暴露 1 个 render node（BDF 0000:03:00.0）——锁域覆盖**可见**设备；兄弟 GPU 不可寻址（`00_RESOURCE_PREFLIGHT.json`）。

## 3.6 Stop 安全

`reference stop [--workspace W] [--run-id R]`：先输出目标（域、holder who/pid/cmdline/workspace、live 状态、BLOCKED 状态）再动作；holder 不属于请求 workspace / 不匹配 run-id → REFUSED（exit 4）；无 holder → exit 1（曾持有）/0。委托 `gpu_lock.graceful_stop`：仅记录的 pid、graceful 信号、拒绝 SIGKILL。实测见上。

## 3.4 CLI 契约（本轮回验项）

- `--workspace` 传播：status/stop 现按请求 workspace 与共享域解析；任意 CWD 调用（测试：从 /tmp 调 status）✓；
- dry-run 无副作用：install dry-run 不 clone/不建 venv；generate dry-run 不建 out-dir（测试 A24 类）✓；
- no-clobber：generate 拒绝非空 out-dir（EXIT_REJECT）✓；
- 退出码：0/1/2/3/4 语义保持（05_CLI_CONTRACT.md）。

## 3.2 依赖可复现性（审计结论，如实分类）

- **Exact pinning**：torch/torchvision/torchaudio（AMD multi-arch index，device-gfx1100 extra）；sglang-rocm-deps.txt（镜像 PR #42106 依赖，剔除 CUDA-only 包）；
- **Wheel 内容哈希**：rc5_prefetch_wheels.py 下载时哈希校验缓存轮子；
- **Full transitive lock**：`NOT_ESTABLISHED`——pip freeze（`pip_freeze_sha256`，冻结收据）是观测证据而非哈希锁定；sglang-rocm-deps.txt 中 `aiohttp`、`datasets`、`build` 等未锁版本条目如实列出；
- **GPU 架构/ROCm userspace/真实计算**：device-gfx1100 extra + import guards + gpu_identity fail-loud 链 + 本轮真实 GPU 计算探针；
- **CUDA torch 替换防护**：AMD index 安装路径 + sglang import guards + CI workspace 测试。
