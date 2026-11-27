"""MoE blocks for the RC5 Q3O judge placement (scripts/rc5_q3o_judge.py).

Context: the official Q3O judge is vLLM + fused MoE kernels with bf16 weights
and bf16 activations (fp32 accumulation). On a 48 GB card the Thinker's
experts (48 layers x 128 experts x 9.44 MB = 1.125 GiB per layer) do not fit
next to each other, and the plain HF Transformers loop is synchronisation
bound (about nine GPU->CPU syncs per layer through ``nonzero()`` / ``where``:
measured 0.21 s per decoded token).

Both blocks below keep the official arithmetic and rounding points:

    router logits  GEMM with fp32 accumulation, stored bf16
    softmax in fp32 -> top-k -> weights normalized in fp32 -> cast to bf16
    gate, up       GEMM (fp32 accumulate), stored bf16
    silu(gate)     bf16;  silu(gate) * up -> bf16
    down           GEMM (fp32 accumulate), stored bf16
    contribution   expert output * bf16 routing weight -> bf16
    output         sum of the selected contributions, stored bf16

Differences that remain (disclosed in the runtime receipt):

* summation order inside a GEMM (fp32 additions may be ordered differently);
* a token's contributions are summed in fp32 and rounded once, where the HF
  loop adds them one by one in bf16 (measured <= 2 bf16 ulp of the largest
  output);
* ties in the top-k are broken by the LOWEST expert index. Router logits are
  bf16 values, so exact ties are common; ``torch.topk`` on
  torch 2.10.0+rocm7.14.1 (the evaluator environment) picks a different tied
  expert on different calls for the same input, which makes a greedy judge
  irreproducible. The tie-breaking rule of the official vLLM kernel is not
  known here, so equivalence for tied inputs is NOT claimed.

* ``BatchedGpuMoeBlock`` — all experts of a layer in two batched GEMMs (bmm),
  unselected outputs are computed and masked away; no host-side loop.
* ``CpuResidentMoeBlock`` — experts of a layer resident on the CPU in fp32,
  only the hit experts computed; one activation round trip per layer.
"""
from __future__ import annotations

import time

import torch
import torch.nn.functional as F


def _bf16(x: torch.Tensor) -> torch.Tensor:
    """round to bf16 precision, kept in fp32 storage (CPU block)."""
    return x.to(torch.bfloat16).to(torch.float32)


def _topk_stable(routing_weights: torch.Tensor, k: int):
    """top-k with a deterministic tie-break: lowest expert index first.

    Also accumulates real-inference boundary-tie statistics (P0.3.4): a tie
    sits ON the top-k boundary when the k-th and (k+1)-th ranked routing
    weights are exactly equal — the selected expert SET is then decided by
    the tie-break rule, not by arithmetic. Counters are GPU tensors updated
    asynchronously (no host sync in the hot path) and read once per
    candidate via read_tie_stats()."""
    order = torch.argsort(routing_weights, dim=-1, descending=True, stable=True)
    selected = order[:, :k]
    global _TIE_ACC
    if order.shape[1] > k:
        w_kth = torch.gather(routing_weights, -1, selected[:, -1:])
        w_next = torch.gather(routing_weights, -1, order[:, k:k + 1])
        ties = w_kth == w_next
        acc = _TIE_ACC.get(routing_weights.device)
        if acc is None:
            acc = torch.zeros(3, dtype=torch.int64, device=routing_weights.device)
            _TIE_ACC[routing_weights.device] = acc
        acc[0] += 1                                   # router calls
        acc[1] += ties.numel()                        # routed token-slots
        acc[2] += ties.sum()                          # async on GPU, no host sync
    return torch.gather(routing_weights, -1, selected), selected


_TIE_ACC: dict = {}


def read_tie_stats() -> dict:
    """Snapshot (and keep) the accumulated tie statistics."""
    out = {}
    for dev, acc in _TIE_ACC.items():
        v = acc.tolist()
        out[str(dev)] = {"router_calls": v[0], "routed_token_slots": v[1],
                         "boundary_ties": v[2],
                         "boundary_tie_rate": round(v[2] / v[1], 8) if v[1] else 0.0}
    return out


def reset_tie_stats() -> None:
    """Replace the accumulators with FRESH tensors (created outside
    inference mode): the first update of a run happens inside
    torch.inference_mode(), which would otherwise brand the accumulator as
    an inference tensor whose later in-place reset from normal mode raises
    RuntimeError."""
    for dev in list(_TIE_ACC):
        _TIE_ACC[dev] = torch.zeros(3, dtype=torch.int64, device=dev)


def _route(num_experts: int, top_k: int, norm_topk_prob: bool, router_logits: torch.Tensor):
    """Routing of HF 4.57.6 SparseMoeBlock.forward, with the deterministic top-k."""
    routing_weights = F.softmax(router_logits, dim=1, dtype=torch.float)
    routing_weights, selected_experts = _topk_stable(routing_weights, top_k)
    if norm_topk_prob:
        routing_weights /= routing_weights.sum(dim=-1, keepdim=True)
    # HF casts the weights back to the input dtype before the expert product
    return routing_weights.to(torch.bfloat16), selected_experts


def install_stable_topk_gpu_moe(block) -> dict:
    """Patch ONE stock HF SparseMoeBlock in place: its forward becomes the
    verbatim HF 4.57.6 loop with exactly one change — torch.topk is replaced
    by _topk_stable so boundary ties resolve deterministically (the plain
    call picked different tied experts across identical runs on
    torch 2.10.0+rocm7.14.1). Weights, module tree and GPU memory layout are
    untouched: NO packing (the batched block's contiguous buffers cannot be
    allocated next to the interleaved live weights of a 48 GB card —
    measured: allocator fragmentation grows ~0.19 GiB per packed layer and
    hits the wall at layer ~21)."""
    import types

    def forward(self, hidden_states):
        F = torch.nn.functional
        B, T, H_ = hidden_states.shape
        hs = hidden_states.view(-1, H_)
        router_logits = self.gate(hs)
        rw = F.softmax(router_logits, dim=1, dtype=torch.float)
        rw, sel = _topk_stable(rw, self.top_k)          # the ONE change
        if self.norm_topk_prob:
            rw = rw / rw.sum(dim=-1, keepdim=True)
        rw = rw.to(hs.dtype)
        final = torch.zeros((B * T, H_), dtype=hs.dtype, device=hs.device)
        mask = F.one_hot(sel, num_classes=self.num_experts).permute(2, 1, 0)
        for e in torch.greater(mask.sum(dim=(-1, -2)), 0).nonzero():
            expert = self.experts[e]
            idx, top_x = torch.where(mask[e].squeeze(0))
            cur = hs[None, top_x].reshape(-1, H_)
            out = expert(cur) * rw[top_x, idx, None]
            final.index_add_(0, top_x, out.to(hs.dtype))
        return final.reshape(B, T, H_), router_logits

    block.forward = types.MethodType(forward, block)
    return {"mode": "stock HF bf16 experts on GPU + _topk_stable tie-break "
                   "(in-place forward patch, no packing, no extra VRAM)",
            "num_experts": int(block.num_experts), "top_k": int(block.top_k),
            "norm_topk_prob": bool(block.norm_topk_prob)}


class BatchedGpuMoeBlock(torch.nn.Module):
    """Drop-in forward for Qwen3OmniMoeThinkerTextSparseMoeBlock on the GPU."""

    def __init__(self, block, free_source: bool = False):
        super().__init__()
        self.num_experts = block.num_experts
        self.top_k = block.top_k
        self.norm_topk_prob = block.norm_topk_prob
        self.gate_w = block.gate.weight.detach().contiguous()                    # [E, H] bf16
        # Pack into PREALLOCATED buffers, expert by expert, and (when
        # free_source=True, the full-model judge path) drop each source
        # expert as soon as it is copied. The naive list-of-cats + stack
        # holds ~2.5 GiB of transients next to the still-live originals and
        # OOMed the first full 34-layer load on the 48 GB card; this way the
        # transient peak is one layer's packed weight block. The copy is
        # bit-exact (same values, same dtype).
        experts = list(block.experts)                   # plain list: item drops free the module
        E = len(experts)
        w0 = experts[0].gate_proj.weight
        I, H = int(w0.shape[0]), int(w0.shape[1])
        dev, dt = w0.device, w0.dtype
        gate_up = torch.empty(E, 2 * I, H, device=dev, dtype=dt)
        down = torch.empty(E, H, I, device=dev, dtype=dt)                # down: Linear(I -> H)
        if free_source:
            block.experts = torch.nn.ModuleList()      # detach the source tree
        for e_idx in range(E):
            e = experts[e_idx]
            gate_up[e_idx, :I].copy_(e.gate_proj.weight.data)
            gate_up[e_idx, I:].copy_(e.up_proj.weight.data)
            down[e_idx].copy_(e.down_proj.weight.data)
            if free_source:
                experts[e_idx] = None                  # free THIS expert now
                # expert modules participate in reference cycles (accelerate
                # hooks): plain refcounting never releases their GPU weights,
                # so without this collect every packed layer kept +1.2 GiB
                # of originals live and the 34-layer load OOMed at layer ~4
                if (e_idx & 31) == 31:
                    import gc
                    gc.collect()
        # bmm consumes the transpose views directly (no contiguous copies:
        # keeping stack + .contiguous().transpose next to the originals also
        # OOMed the 48 GB card); same dot products, same arithmetic.
        self.gate_up = gate_up                                           # [E, 2I, H]
        self.down = down                                                 # [E, I, H]
        self.stats = {"layer_forwards": 0, "gpu_seconds": 0.0}

    @property
    def gate_up_t(self):
        return self.gate_up.transpose(1, 2)                                      # view [E, H, 2I]

    @property
    def down_t(self):
        return self.down.transpose(1, 2)                                         # view [E, H_out, I]

    def extra_repr(self) -> str:
        return f"(batched GPU experts: {self.num_experts})"

    def forward(self, hidden_states: torch.Tensor):
        t0 = time.perf_counter()
        batch_size, sequence_length, hidden_dim = hidden_states.shape
        x = hidden_states.reshape(-1, hidden_dim)                               # [T, H]
        T = x.shape[0]
        E = self.num_experts
        router_logits = F.linear(x, self.gate_w)                                # [T, E] bf16
        rw_bf16, selected = _route(E, self.top_k, self.norm_topk_prob, router_logits)
        # all experts, two batched GEMMs (no host loop, no synchronisation)
        gu = torch.bmm(x.unsqueeze(0).expand(E, T, hidden_dim), self.gate_up_t)  # [E, T, 2I]
        gate, up = gu.chunk(2, dim=-1)
        mid = F.silu(gate) * up                                                  # bf16
        out = torch.bmm(mid, self.down_t)                                        # [E, T, H]
        w = torch.zeros(E, T, dtype=torch.float32, device=selected.device)
        w.scatter_add_(0, selected.t().contiguous(), rw_bf16.t().contiguous().to(torch.float32))
        final = (out * w.to(torch.bfloat16).unsqueeze(-1)).sum(dim=0)            # fp32 accumulate -> bf16
        final = final.to(hidden_states.dtype).reshape(batch_size, sequence_length, hidden_dim)
        self.stats["layer_forwards"] += 1
        self.stats["gpu_seconds"] += time.perf_counter() - t0
        return final, router_logits


class CpuResidentMoeBlock(torch.nn.Module):
    """Drop-in forward for Qwen3OmniMoeThinkerTextSparseMoeBlock on the CPU."""

    def __init__(self, block, log=None):
        super().__init__()
        self.num_experts = block.num_experts
        self.top_k = block.top_k
        self.norm_topk_prob = block.norm_topk_prob
        self.gate_w = block.gate.weight.detach().to("cpu", torch.float32).contiguous()   # [E, H]
        self.gate_up = []      # per expert: [2*I, H] fp32 (gate rows then up rows)
        self.down = []         # per expert: [H, I] fp32
        for e in block.experts:
            self.gate_up.append(torch.cat([e.gate_proj.weight.detach(), e.up_proj.weight.detach()],
                                          dim=0).to("cpu", torch.float32).contiguous())
            self.down.append(e.down_proj.weight.detach().to("cpu", torch.float32).contiguous())
        self.stats = {"layer_forwards": 0, "cpu_seconds": 0.0}

    def extra_repr(self) -> str:
        return f"(cpu-resident experts: {self.num_experts} x fp32)"

    def forward(self, hidden_states: torch.Tensor):
        t0 = time.perf_counter()
        batch_size, sequence_length, hidden_dim = hidden_states.shape
        out_device = hidden_states.device
        # bf16 values held in fp32: products are exact, accumulation is fp32 (as in a bf16 GEMM)
        x = hidden_states.reshape(-1, hidden_dim).to("cpu", torch.float32)       # [T, H]
        router_logits = _bf16(F.linear(x, self.gate_w))                          # stored bf16
        rw, selected = _route(self.num_experts, self.top_k, self.norm_topk_prob, router_logits)
        final = torch.zeros((x.shape[0], hidden_dim), dtype=torch.float32)
        flat = selected.reshape(-1)
        counts = torch.bincount(flat, minlength=self.num_experts)
        hit = counts.nonzero().flatten().tolist()
        if hit:
            token_idx = torch.arange(flat.numel(), device="cpu") // self.top_k
            k_idx = torch.arange(flat.numel(), device="cpu") % self.top_k
            order = torch.argsort(flat, stable=True)
            bounds = torch.cumsum(counts, 0)
            start = 0
            rw_f = rw.to(torch.float32)
            for e in hit:
                end = int(bounds[e])
                sel = order[start:end]
                start = end
                tok, k = token_idx[sel], k_idx[sel]
                state = x[tok]                                                   # [n, H]
                gate, up = F.linear(state, self.gate_up[e]).chunk(2, dim=-1)
                mid = _bf16(_bf16(F.silu(_bf16(gate))) * _bf16(up))              # bf16 activation flow
                out = _bf16(F.linear(mid, self.down[e]))
                final.index_add_(0, tok, _bf16(out * rw_f[tok, k, None]))
        final = final.to(torch.bfloat16).to(out_device).reshape(batch_size, sequence_length, hidden_dim)
        router_logits = router_logits.to(torch.bfloat16).to(out_device)
        self.stats["layer_forwards"] += 1
        self.stats["cpu_seconds"] += time.perf_counter() - t0
        return final, router_logits
