"""
gate/trust_gate.py — the complete Trust Gate (signals + decision), plugged into the graph.

make_trust_gate(llm, params) -> a function gate(candidate, state) called by the `trust_gate` node in src/graph.py.

Two deliberately separate stages:
  compute_signals()   T_source, C_content, R_contradiction, R_pattern  (LLM calls happen here, results are cached)
  decide_candidate()  T_final + accept/quarantine/reject from the signals + GateParams (no LLM)
This way thresholds and ablations can be recomputed from the stored signals (gate_decisions).

The gate does NOT read attack labels (is_poison, poison_value, poison_keys, truth_keys, gold_answer): candidates
from memory_writer simply do not carry those fields.
"""
from dataclasses import dataclass

from gate.llm_signals import N_NEIGHBORS, content_confidence, contradiction
from gate.scoring import decide, pattern_hits, source_span, source_trust, trust_score


@dataclass(frozen=True)
class GateParams:
    mode: str = "trust"            # "trust" = Trust Gate; "content_only" = content-only baseline gate (C_content only)
    theta_accept: float = 0.5      # placeholder default; tuned per model on dev (config/gate_thresholds.yaml)
    theta_reject: float = 0.2      # placeholder default; tuned per model on dev (config/gate_thresholds.yaml)
    lambda_r: float = 1.0
    lambda_t: float = 0.0          # Δt = 0 in this dataset, so this has no effect
    use_source_trust: bool = True  # ablation: False -> T_source = 1
    use_poison_risk: bool = True   # ablation: False -> R_poison = 0

    @property
    def needs_contradiction(self):
        return self.mode == "trust" and self.use_poison_risk


def compute_signals(cand, chunk_text, store, llm, params):
    span = source_span(cand["content"], chunk_text)
    hits = pattern_hits(span)
    r_contra = None
    if params.needs_contradiction:
        neighbors = [m["content"] for m in store.retrieve(cand["content"], k=N_NEIGHBORS)] if store.count() else []
        r_contra = contradiction(cand["content"], neighbors, llm)
    return {"t_source": source_trust(cand["source"]),
            "c_content": content_confidence(cand["content"], chunk_text, llm),
            "r_contradiction": r_contra,
            "r_pattern": 1.0 if hits else 0.0,
            "patterns": ",".join(hits),
            "age_days": 0.0}


def decide_candidate(sig, params):
    """Returns (T_final, decision). Pure function, also used to recompute thresholds/ablations."""
    if params.mode == "content_only":
        score = sig["c_content"]
    else:
        t_src = sig["t_source"] if params.use_source_trust else 1.0
        r = max(sig["r_contradiction"] or 0.0, sig["r_pattern"]) if params.use_poison_risk else 0.0
        score = trust_score(t_src, sig["c_content"], r, sig.get("age_days", 0.0), params.lambda_t, params.lambda_r)
    return score, decide(score, params.theta_accept, params.theta_reject)


def make_trust_gate(llm, params=GateParams()):
    def gate(cand, state):
        sig = compute_signals(cand, cand["_chunk_text"], state["store"], llm, params)
        score, decision = decide_candidate(sig, params)
        return {**cand, **sig, "t_final": round(score, 4), "decision": decision, "gate_mode": params.mode}
    return gate
