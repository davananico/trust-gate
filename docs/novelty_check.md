## Closest work found

| Work | What it does | Overlap with this project | Read at |
| --- | --- | --- | --- |
| **MIVL** — J. Sheoran, 2026, *MIVL: a memory integrity verification layer for detecting and mitigating poisoning attacks in agentic AI systems*, SSRN 6880480 (not peer reviewed) | Write-time layer that scores each candidate memory with semantic drift, directive patterns, temporal behaviour, provenance and cross-memory contradiction, combined into a weighted Memory Integrity Score that blocks, quarantines, sanitizes or flags | **Very high**: provenance + directive patterns + time + contradiction → one score → accept/quarantine/reject is essentially the Trust Gate formula | Only as described in the related work of MemSentry (arXiv 2609.08747); SSRN page returned 403 |
| **SAGE-Mem** — A. Pandey, *Before It Persists: Write-Time Defense for Multimodal Agent Memory*, ICML 2026 | Write-time: evidence promoted to belief only when supported, independent and non-conflicting | High: write-time, conflict-based admission; uses **LoCoMo-Adv** (adversarial LoCoMo-10); reports the utility cost (benign completion 0.642 → 0.460) | Abstract (icml.cc) |
| **MemPoison** — Gao et al., arXiv 2607.14651 (Jul/Oct 2026) | Benchmark (1,227 cases, 10 LLM families) with write-time baselines: consistency check, LLM-judge write check, novelty filter | High on evaluation: shows write-time consistency checks stop direct single-record attacks (L1 BCR 4.8%) but not multi-record (L2) or dormant (L3) attacks | Abstract + result table |
| **TMA-NM** — Y. Louck, arXiv 2606.24322 (Jun 2026) | Proves content- and lineage-based defenses are unsound under "laundering"; proposes origin-bound authority | Medium: argues the Trust Gate's family cannot be sound against an adaptive attacker | Abstract |
| **SMSR** — arXiv 2606.12703 (Jun 2026) | HMAC provenance tags at write time + certified retrieval-time voting | Medium: provenance at write time | Search summary |
| **MemSentry** — arXiv 2609.08747 (Sep 2026) | Pre-admission pipeline: provenance/source authority + dependency graph + classifier, no LLM, no contradiction check | Medium: pre-storage + provenance | Related-work section |

## Positioning (decided by the author, 17 Nov 2026: the Trust Gate stays unchanged)

The gate is kept as designed. The paper must not claim the *combination of signals* is new (MIVL lists similar
signals), so the difference is stated in what the Trust Gate does differently and in what is shown about it.
Everything said about MIVL below is from a second-hand description and must be checked against its full text.

| Point | MIVL (as described) | Trust Gate |
| --- | --- | --- |
| How signals combine | Weighted Memory Integrity Score: a high value on one signal can offset a low one | `min(T_source, C_content)`: the source is a **cap**. No content score can lift a memory above its source's trust ("convincing text from an untrusted source is not trusted"). Tested: removing source trust weakens the gate (ablation) |
| Where patterns are checked | On the candidate memory (not stated otherwise) | On the **source turn** that produced the candidate (`source_span`), because the writer LLM was observed to drop assertion phrases when summarizing |
| Memory vs permission | Not described | Authorization is a separate allowlist, never granted by memory; AD4 shows why this matters when the gate itself is bypassed |
| Threshold selection | Not described | Tuned on dev only, with external-source FRR weighted equally to stop the gate "winning" by rejecting every external source (circular-reasoning control); test run once with checksummed settings |
| Evaluation | Not described in the source we saw | 4 open LLMs each running writer + gate + agent; 3 attack types + an authorization attack; clean external pages identical to attack pages; adaptive white-box attacks; a second dataset with legitimate knowledge updates; 95% Wilson CIs; failure analysis |

What to claim: a cap-based, provenance-bounded admission rule, and a controlled evaluation of when it works, what it
costs and how it fails. What not to claim: that combining these signals is new.

## Contributions to argue (to be checked against the full texts)

  1. A controlled evaluation of such a gate on **four open models running the whole pipeline**, showing the gate's
     benefit and cost are bounded by the model acting as contradiction judge (qwen3/gemma4 ≈ 2% FRR vs olmo-3 63%).
  2. The **failure analysis**: poison, legitimate updates and recurring events are indistinguishable to a write-time
     contradiction check ("same question, different answer").
  3. The **circular-reasoning control** (clean external pages identical to A3 pages, external FRR weighted in
     threshold selection).
  4. **Adaptive attacks** built from the gate's own code (`docs/adaptive_attacks_spec.md`): these test the
     claims that MemPoison and TMA-NM make in general, on a concrete gate.
- Required comparisons: cite MIVL, SAGE-Mem, MemPoison and TMA-NM; discuss LoCoMo-Adv (possibly a better second
  dataset or a direct comparison point, since it is also built on LoCoMo).
