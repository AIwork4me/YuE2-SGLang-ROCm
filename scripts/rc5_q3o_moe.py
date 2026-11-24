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
    """top-k with a deterministic tie-break: lowest expert index first."""
    order = torch.argsort(routing_weights, dim=-1, descending=True, stable=True)
    selected = order[:, :k]
    return torch.gather(routing_weights, -1, selected), selected


def _route(num_experts: int, top_k: int, norm_topk_prob: bool, router_logits: torch.Tensor):
    """Routing of HF 4.57.6 SparseMoeBlock.forward, with the deterministic top-k."""
    routing_weights = F.softmax(router_logits, dim=1, dtype=torch.float)
    routing_weights, selected_experts = _topk_stable(routing_weights, top_k)
    if norm_topk_prob:
        routing_weights /= routing_weights.sum(dim=-1, keepdim=True)
    # HF casts the weights back to the input dtype before the expert product
    return routing_weights.to(torch.bfloat16), selected_experts


class BatchedGpuMoeBlock(torch.nn.Module):
    """Drop-in forward for Qwen3OmniMoeThinkerTextSparseMoeBlock on the GPU."""

    def __init__(self, block):
        super().__init__()
        self.num_experts = block.num_experts
        self.top_k = block.top_k
        self.norm_topk_prob = block.norm_topk_prob
        self.gate_w = block.gate.weight.detach().contiguous()                    # [E, H] bf16
        # stack the per-expert weights: same tensors' values, one block of memory
        gu = torch.stack([torch.cat([e.gate_proj.weight.detach(), e.up_proj.weight.detach()], 0)
                          for e in block.experts], 0).contiguous()                # [E, 2I, H]
        self.gate_up_t = gu.transpose(1, 2).contiguous()                         # [E, H, 2I]
        del gu
        dn = torch.stack([e.down_proj.weight.detach() for e in block.experts], 0).contiguous()
        self.down_t = dn.transpose(1, 2).contiguous()                            # [E, I, H]
        del dn
        self.stats = {"layer_forwards": 0, "gpu_seconds": 0.0}

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
