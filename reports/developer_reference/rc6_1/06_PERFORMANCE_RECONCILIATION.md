# M6.1 — Performance Evidence Reconciliation

{
 "schema": "yue2-rc6_1-performance-reconciliation/1",
 "generated_at_utc": "2026-11-27T23:25:58Z",
 "contradiction_investigated": "RC6 06_PERFORMANCE_REFERENCE.md stated 'Peak device VRAM 29.7 GiB' next to 'torch-allocated VRAM ~47 GiB card saturation' for the same generation campaign — same device, same scope: a contradiction.",
 "root_cause": "the '~47 GiB' figure is the CARD'S TOTAL CAPACITY (total_memory_gib = 47.98 in the gpu_identity receipts — e.g. vram_gib=47.98 in lifecycle logs), misdescribed in RC6 as torch-allocated usage. No torch-allocated ~47 GiB measurement exists anywhere in the raw evidence; the server's own peak_memory_mb telemetry is 0.0 for all 384 candidates (known ROCm telemetry gap).",
 "reconciled_numbers": {
  "generation_peak_card_total_vram_gib": {
   "value": 29.68,
   "source": "generation_summary.json memory.peak_vram_bytes = 31865282560",
   "scope": "card-total usage, all processes, sampled via /sys/class/drm/card1/device"
  },
  "card_total_capacity_gib": {
   "value": 47.98,
   "source": "mem_info_vram_total = 51522830336 (gpu_identity receipt)",
   "scope": "capacity — NOT usage"
  },
  "per_candidate_vram_delta_gib": {
   "mean": 8.8,
   "P95": 11.71,
   "max": 17.89,
   "source": "journal candidate_vram_delta_bytes, n=384",
   "scope": "generation increment above the server baseline"
  },
  "implied_server_baseline_gib": {
   "value": 11.79,
   "derivation": "peak card-total 29.68 - max candidate delta 17.89",
   "consistency": "consistent with YuE2-3B BF16 weights (MoT 7.26 GiB + VAE 0.53 GiB) + runtime pools"
  },
  "q3o_peak_torch_allocated_gib": {
   "value": 42.41,
   "source": "RC5.1 Q3O runtime receipt (torch-allocated metric)",
   "scope": "Q3O judge process only — a legitimately different metric family"
  }
 },
 "card1_mapping_verified": "/sys/class/drm/card1 -> PCI 0000:03:00.0 (the single exposed amdgpu render node; gpu_identity closed chain binds framework device -> BDF -> render node). card1 was NOT assumed: it was resolved. The host has 8 amdgpu functions; this container exposes exactly one.",
 "historical_torch_allocated_generation": "HISTORICAL_PEAK_VRAM_TORCH_ALLOCATED_NOT_ESTABLISHED — peak_memory_mb telemetry returned 0.0 (ROCm gap); only the card-total sampler and per-candidate deltas exist. The RC6 '~47 GiB torch-allocated' line is RETRACTED (superseding notice; the frozen raw data is untouched).",
 "rc6_1_instrumented_pilot": "the fresh-workspace pilot (M5) collects a unified timeline: card-total VRAM, per-candidate deltas, and process-mapped torch.allocated where the runtime exposes it — reported as 06_GPU_MEMORY_TELEMETRY.json with explicit metric families, never mixed.",
 "percentile_consistency": "see 06_PERCENTILE_REFERENCE.json — RC6's P95/P99 figures came from an ad-hoc undocumented quantile formula; RC6.1 recomputed all percentiles from the frozen raw CSV with the DECLARED NumPy linear-interpolation estimator."
}
