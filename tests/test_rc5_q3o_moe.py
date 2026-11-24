"""MoE placement blocks for the Q3O judge (RC5 M7).

The reference is the verbatim HF 4.57.6 SparseMoeBlock loop. Router logits
are bf16 values, so exact ties are common; where a tie sits on the top-k
boundary the selected expert set is a tie-breaking decision, not arithmetic.
Equivalence is therefore asserted on inputs WITHOUT a boundary tie (the
precondition is checked, never assumed), and the tie-breaking rule is tested
on its own.

The GPU block is compared on a real accelerator when one is available and
skipped otherwise (never reported as a GPU pass).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_M = None


def _skip_without_torch():
    """importorskip, robust both to a missing torch (CI: ModuleNotFoundError
    -> skip) and to a torch installation that raises on import (broken
    install: newer pytest propagates the ImportError -> skip explicitly)."""
    try:
        return pytest.importorskip("torch")
    except ImportError:
        pytest.skip("torch is not importable on this host")


def _module(torch):
    """Load scripts/rc5_q3o_moe.py lazily: it imports torch at module level and
    CI has no torch, so the import must happen inside the tests (which skip
    honestly without torch), never at collection time."""
    global _M
    if _M is None:
        spec = importlib.util.spec_from_file_location("rc5_q3o_moe", REPO / "scripts" / "rc5_q3o_moe.py")
        _M = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_M)
    return _M


def _tiny_block(torch, E=8, k=3, H=64, I=32):
    class MLP(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gate_proj = torch.nn.Linear(H, I, bias=False)
            self.up_proj = torch.nn.Linear(H, I, bias=False)
            self.down_proj = torch.nn.Linear(I, H, bias=False)

        def forward(self, x):
            return self.down_proj(torch.nn.functional.silu(self.gate_proj(x)) * self.up_proj(x))

    class Block(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.num_experts, self.top_k, self.norm_topk_prob = E, k, True
            self.gate = torch.nn.Linear(H, E, bias=False)
            self.experts = torch.nn.ModuleList(MLP() for _ in range(E))

        def forward(self, hidden_states):      # verbatim HF 4.57.6 loop
            F = torch.nn.functional
            B, T, H_ = hidden_states.shape
            hs = hidden_states.view(-1, H_)
            router_logits = self.gate(hs)
            rw = F.softmax(router_logits, dim=1, dtype=torch.float)
            rw, sel = torch.topk(rw, self.top_k, dim=-1)
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
    return Block()


def _boundary_ties(torch, ref, x):
    """rows whose k-th and (k+1)-th routing probability are exactly equal."""
    logits = ref.gate(x.reshape(-1, x.shape[-1]))
    p = torch.sort(torch.nn.functional.softmax(logits, dim=1, dtype=torch.float), 1, descending=True).values
    return int((p[:, ref.top_k - 1] == p[:, ref.top_k]).sum())


def _tie_free(torch, ref, shape, scale=0.5):
    dev = ref.gate.weight.device
    torch.manual_seed(0)
    x = (torch.randn(*shape, device=dev) * scale).to(torch.bfloat16)
    for _ in range(500):
        if _boundary_ties(torch, ref, x) == 0:
            return x
        x = (x.float() + 0.05 * torch.randn(*shape, device=dev)).to(torch.bfloat16)   # scaling cannot break ties
    raise AssertionError("no tie-free input found")


def _order_key(torch, t):
    """monotonic integer key of bf16 values, for distances in bf16 ulp."""
    bits = t.to(torch.bfloat16).view(torch.int16).to(torch.int32)
    return torch.where(bits < 0, -32768 - bits, bits)


def _dev(torch):
    return torch.device("cuda", 0) if torch.cuda.is_available() else torch.device("cpu")


def test_stable_topk_gpu_patch_matches_hf_loop_and_pins_ties():
    """install_stable_topk_gpu_moe: the in-place patched stock HF block must
    match the verbatim HF loop on tie-free inputs and must resolve crafted
    boundary ties deterministically (the plain torch.topk it replaces did
    not, on torch 2.10.0+rocm7.14.1)."""
    torch = _skip_without_torch()
    dev = _dev(torch)
    ref = _tiny_block(torch, E=8, k=3, H=64, I=32).to(dev, torch.bfloat16)
    patched = _tiny_block(torch, E=8, k=3, H=64, I=32).to(dev, torch.bfloat16)
    patched.load_state_dict(ref.state_dict())                 # identical weights
    info = _module(torch).install_stable_topk_gpu_moe(patched)
    assert info["top_k"] == 3 and info["norm_topk_prob"] is True
    x = _tie_free(torch, ref, (2, 37, 64))
    assert _boundary_ties(torch, ref, x) == 0
    with torch.no_grad():
        y_ref, l_ref = ref(x)                                  # verbatim HF loop
        y, l = patched(x)
        y_again, _ = patched(x)
    assert torch.equal(_order_key(torch, l), _order_key(torch, l_ref))       # same router logits
    assert torch.equal(_order_key(torch, y), _order_key(torch, y_ref))       # bit-exact on ties-free
    assert torch.equal(y, y_again)                                            # deterministic
    # crafted boundary tie: same input through both, patched picks lowest index
    ref1 = _tiny_block(torch, E=8, k=1, H=64, I=32).to(dev, torch.bfloat16)
    pat1 = _tiny_block(torch, E=8, k=1, H=64, I=32).to(dev, torch.bfloat16)
    pat1.load_state_dict(ref1.state_dict())
    _module(torch).install_stable_topk_gpu_moe(pat1)
    xt, a, b = _crafted_boundary_tie(torch, ref1, dev)
    with torch.no_grad():
        expected = _oracle_output(torch, ref1, xt)             # independent reference
        y1, _ = pat1(xt)
    assert a != b
    ulp = (_order_key(torch, y1.reshape(expected.shape)) - _order_key(torch, expected)).abs()
    assert int(ulp.max()) <= 1 and (ulp == 0).float().mean().item() >= 0.999


def test_topk_stable_breaks_ties_by_lowest_index():
    torch = _skip_without_torch()
    dev = _dev(torch)
    probs = torch.tensor([[0.30, 0.30, 0.10, 0.30, 0.00, 0.20, 0.20, 0.05],
                          [0.25, 0.25, 0.25, 0.25, 0.00, 0.00, 0.00, 0.00]], device=dev)
    values, selected = _module(torch)._topk_stable(probs, 3)
    assert selected.tolist() == [[0, 1, 3], [0, 1, 2]]            # lowest index first among equals
    assert torch.allclose(values, torch.tensor([[0.3, 0.3, 0.3], [0.25, 0.25, 0.25]], device=dev))
    for _ in range(50):                                            # same answer on every call
        assert torch.equal(_module(torch)._topk_stable(probs, 3)[1], selected)


def test_route_matches_hf_formulas_on_tie_free_logits():
    torch = _skip_without_torch()
    dev = _dev(torch)
    F = torch.nn.functional
    E, k, T = 16, 4, 256
    torch.manual_seed(1)
    logits = (torch.randn(T, E) * 2.0).to(torch.bfloat16).to(dev)
    for _ in range(500):
        p = torch.sort(F.softmax(logits, dim=1, dtype=torch.float), 1, descending=True).values
        if not bool((p[:, k - 1] == p[:, k]).any()):
            break
        logits = (logits.float() + 0.05 * torch.randn(T, E, device=dev)).to(torch.bfloat16)
    else:
        raise AssertionError("no tie-free logits found")
    hf_w = F.softmax(logits, dim=1, dtype=torch.float)            # HF formulas, verbatim order
    hf_w, hf_sel = torch.topk(hf_w, k, dim=-1)
    hf_w = (hf_w / hf_w.sum(dim=-1, keepdim=True)).to(torch.bfloat16)
    w, sel = _module(torch)._route(E, k, True, logits)
    assert torch.equal(torch.sort(sel, dim=1).values, torch.sort(hf_sel, dim=1).values)   # same experts
    full, hf_full = torch.zeros(T, E, device=dev), torch.zeros(T, E, device=dev)
    full.scatter_(1, sel, w.float())                              # same weight for the same expert
    hf_full.scatter_(1, hf_sel, hf_w.float())
    assert torch.equal(full, hf_full)


def test_route_normalises_weights():
    torch = _skip_without_torch()
    E, k, T = 8, 3, 32
    torch.manual_seed(2)
    logits = (torch.randn(T, E) * 0.5).to(torch.bfloat16)
    w, sel = _module(torch)._route(E, k, True, logits)
    assert torch.allclose(w.float().sum(dim=-1), torch.ones(T), atol=2e-2)   # bf16 weights sum to ~1
    w_raw, _ = _module(torch)._route(E, k, False, logits)
    assert w_raw.float().sum(dim=-1).max() < 0.9                               # unnormalised top-k mass < 1


def _crafted_boundary_tie(torch, ref, dev):
    """One token whose two largest logits differ in fp32 but round to the SAME
    bf16 value, with the fp32 winner at the HIGHER expert index: rounding must
    create the tie and the defined rule must resolve it to the lower index.
    Both logits stay well inside one bf16 interval so that the ~1e-7 relative
    difference between the reference bf16 GEMM and the block's GEMM cannot
    flip the rounding (the CPU block rounds an fp32 GEMM)."""
    import math
    H = ref.gate.weight.shape[1]
    def spacing(v):
        return 2.0 ** (math.floor(math.log2(abs(v))) - 8)
    def to_bf16(v):
        return torch.tensor(v).to(torch.bfloat16).float().item()
    torch.manual_seed(3)
    x = (torch.randn(1, 1, H, device=dev) * 0.5).to(torch.bfloat16)
    for _ in range(8000):
        hs = x.reshape(-1, H)
        logits32 = torch.nn.functional.linear(hs.float(), ref.gate.weight.float())   # pre-rounding fp32 GEMM
        logits16 = ref.gate(hs)                                                       # bf16, as routed
        a, b = torch.topk(logits32, 2, dim=-1).indices[0].tolist()                    # fp32 order
        la, lb = logits32[0, a].item(), logits32[0, b].item()
        if (a > b and la != lb and bool(logits16[0, a] == logits16[0, b])):
            u = spacing(la)
            g = to_bf16(la)
            mid = 0.5 * (g + to_bf16(g + 1.5 * u))          # next grid point above g
            mid_lo = 0.5 * (g + to_bf16(g - 1.5 * u))       # grid point below g
            if (abs(la - lb) <= 0.25 * u
                    and min(abs(la - mid), abs(la - mid_lo)) > 0.05 * u
                    and min(abs(lb - mid), abs(lb - mid_lo)) > 0.05 * u):
                return x, a, b
        x = (x.float() + 0.03 * torch.randn(1, 1, H, device=dev)).to(torch.bfloat16)
    raise AssertionError("no robust crafted boundary tie found")


def _oracle_output(torch, ref, x):
    """Independent mathematical reference for the block output. It does NOT
    call the module under test (no _route / _topk_stable): probabilities are
    the fp32 softmax of the bf16 router logits, the top-k set is descending
    probability with ties broken to the LOWER expert index (a stable sort of
    the NEGATED probability — a different mechanism than the module's
    descending argsort+gather), weights are renormalised in fp32 and rounded
    to bf16, contributions use the HF reference expert modules and are summed
    in fp32 with one final rounding."""
    H = ref.gate.weight.shape[1]
    hs = x.reshape(-1, H)
    logits = ref.gate(hs)                                            # bf16, as routed
    probs = torch.nn.functional.softmax(logits, dim=1, dtype=torch.float)
    k = ref.top_k
    sel = torch.argsort(-probs, dim=1, stable=True)[:, :k]           # ties -> lower index first
    w = probs.gather(1, sel)
    if ref.norm_topk_prob:
        w = (w / w.sum(dim=-1, keepdim=True)).to(torch.bfloat16)
    total = torch.zeros_like(hs, dtype=torch.float32)
    for kk in range(k):
        e = int(sel[0, kk])
        total += (ref.experts[e](hs) * w[0, kk]).float()
    return total.to(torch.bfloat16)


@pytest.mark.parametrize("block_name", ["CpuResidentMoeBlock", "BatchedGpuMoeBlock"])
def test_block_rounds_router_logits_to_bf16_before_routing(block_name):
    """Pins the rounding of router logits to bf16 (the deviation that affected
    the two retained Q3O pilot runs) and the defined tie-break that follows."""
    torch = _skip_without_torch()
    if block_name == "BatchedGpuMoeBlock" and not torch.cuda.is_available():
        pytest.skip("no accelerator on this host")
    dev = _dev(torch)
    ref = _tiny_block(torch, E=8, k=1, H=64, I=32).to(dev, torch.bfloat16)
    x, a, b = _crafted_boundary_tie(torch, ref, dev)
    with torch.no_grad():
        expected = _oracle_output(torch, ref, x)
        y, _ = getattr(_module(torch), block_name)(ref)(x)
    assert a != b
    ulp = (_order_key(torch, y.reshape(expected.shape)) - _order_key(torch, expected)).abs()
    assert int(ulp.max()) <= 1, (a, b, int(ulp.max()))       # a full expert swap would be ~30000 ulp
    assert (ulp == 0).float().mean().item() >= 0.999


@pytest.mark.parametrize("block_name", ["CpuResidentMoeBlock", "BatchedGpuMoeBlock"])
def test_rounding_points_are_bit_exact_for_a_single_expert(block_name):
    """top_k = 1: one contribution per token, no summation-order freedom, so
    the block must reproduce the HF loop bit for bit (up to rare last-bit
    differences of fp32 GEMM accumulation). This is what pins the bf16
    rounding points of gate, up, silu and down."""
    torch = _skip_without_torch()
    if block_name == "BatchedGpuMoeBlock" and not torch.cuda.is_available():
        pytest.skip("no accelerator on this host")
    dev = _dev(torch)
    ref = _tiny_block(torch, E=8, k=1, H=64, I=32).to(dev, torch.bfloat16)
    x = _tie_free(torch, ref, (1, 256, 64))
    assert _boundary_ties(torch, ref, x) == 0
    with torch.no_grad():
        y_ref, l_ref = ref(x)
        y, logits = getattr(_module(torch), block_name)(ref)(x)
    assert torch.equal(_order_key(torch, logits), _order_key(torch, l_ref))        # router logits: bit-exact
    assert torch.isfinite(y.float()).all() and y.dtype == torch.bfloat16
    ulp = (_order_key(torch, y.reshape(y_ref.shape)) - _order_key(torch, y_ref)).abs()
    assert (ulp == 0).float().mean().item() >= 0.999, (ulp == 0).float().mean().item()
    assert int(ulp.max()) <= 1


@pytest.mark.parametrize("block_name", ["CpuResidentMoeBlock", "BatchedGpuMoeBlock"])
def test_block_matches_reference_loop(block_name):
    """top_k = 3 on a tie-free input. Remaining difference: contributions are
    summed in fp32 and rounded once where HF adds them in bf16 (<= 2 ulp)."""
    torch = _skip_without_torch()
    if block_name == "BatchedGpuMoeBlock" and not torch.cuda.is_available():
        pytest.skip("no accelerator on this host")
    dev = _dev(torch)
    ref = _tiny_block(torch, E=8, k=3, H=64, I=32).to(dev, torch.bfloat16)
    x = _tie_free(torch, ref, (2, 37, 64))
    assert _boundary_ties(torch, ref, x) == 0
    with torch.no_grad():
        y_ref, l_ref = ref(x)
        y, logits = getattr(_module(torch), block_name)(ref)(x)
        y1, _ = getattr(_module(torch), block_name)(ref)(x[:1, :1])                 # decode shape (one token)
    assert torch.equal(_order_key(torch, logits), _order_key(torch, l_ref))
    scale = y_ref.float().abs().max().item()
    assert (y.float() - y_ref.float()).abs().max().item() / scale < 0.02
    assert y1.shape == (1, 1, 64) and torch.isfinite(y1.float()).all()
    for _ in range(5):                                                 # deterministic across calls
        y_again, _ = getattr(_module(torch), block_name)(ref)(x)
        assert torch.equal(y_again, y)
