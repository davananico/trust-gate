## Closest work found

| Work | What it does | Overlap with this project | Read at |
| --- | --- | --- | --- |
| **MIVL** — J. Sheoran, 2026, *MIVL: a memory integrity verification layer for detecting and mitigating poisoning attacks in agentic AI systems*, SSRN 6880480 (not peer reviewed) | Write-time layer that scores each candidate memory with semantic drift, directive patterns, temporal behaviour, provenance and cross-memory contradiction, combined into a weighted Memory Integrity Score that blocks, quarantines, sanitizes or flags | **Very high**: provenance + directive patterns + time + contradiction → one score → accept/quarantine/reject is essentially the Trust Gate formula | Only as described in the related work of MemSentry (arXiv 2609.08747); SSRN page returned 403 |
| **SAGE-Mem** — A. Pandey, *Before It Persists: Write-Time Defense for Multimodal Agent Memory*, ICML 2026 | Write-time: evidence promoted to belief only when supported, independent and non-conflicting | High: write-time, conflict-based admission; uses **LoCoMo-Adv** (adversarial LoCoMo-10); reports the utility cost (benign completion 0.642 → 0.460) | Abstract (icml.cc) |
| **MemPoison** — Gao et al., arXiv 2607.14651 (Jul/Oct 2026) | Benchmark (1,227 cases, 10 LLM families) with write-time baselines: consistency check, LLM-judge write check, novelty filter | High on evaluation: shows write-time consistency checks stop direct single-record attacks (L1 BCR 4.8%) but not multi-record (L2) or dormant (L3) attacks | Abstract + result table |
| **TMA-NM** — Y. Louck, arXiv 2606.24322 (Jun 2026) | Proves content- and lineage-based defenses are unsound under "laundering"; proposes origin-bound authority | Medium: argues the Trust Gate's family cannot be sound against an adaptive attacker | Abstract |
| **SMSR** — arXiv 2606.12703 (Jun 2026) | HMAC provenance tags at write time + certified retrieval-time voting | Medium: provenance at write time | Search summary |
| **MemSentry** — arXiv 2609.08747 (Sep 2026) | Pre-admission pipeline: provenance/source authority + dependency graph + classifier, no LLM, no contradiction check | Medium: pre-storage + provenance | Related-work section |

## Consequence for the paper

- The claim "a security-oriented, provenance-aware pre-storage gate combining source trust, content confidence,
  temporal validity and poisoning risk" is **no longer a novel mechanism**: MIVL describes nearly the same
  combination. The sentence "no identical combination was found" must be removed.
- What may still be a contribution (to be checked against the full texts):
  1. A controlled evaluation of such a gate on **four open models running the whole pipeline**, showing the gate's
     benefit and cost are bounded by the model acting as contradiction judge (qwen3/gemma4 ≈ 2% FRR vs olmo-3 63%).
  2. The **failure analysis**: poison, legitimate updates and recurring events are indistinguishable to a write-time
     contradiction check ("same question, different answer").
  3. The **circular-reasoning control** (clean external pages identical to A3 pages, external FRR weighted in
     threshold selection).
  4. **Adaptive attacks** built from the gate's own code (`docs/adaptive_attacks_spec.md`): these test the
     claims that MemPoison and TMA-NM make in general, on a concrete gate.
- Likely framing: an *empirical study of a write-time trust gate and how it fails*, not a new defense.
- Required comparisons: cite MIVL, SAGE-Mem, MemPoison and TMA-NM; discuss LoCoMo-Adv (possibly a better second
  dataset or a direct comparison point, since it is also built on LoCoMo).
