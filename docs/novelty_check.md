# Novelty check — closest related work and positioning

Started 17 Nov 2026 for the paper version; most entries are read at abstract level only (column "Read at").

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
| How signals combine | Weighted Memory Integrity Score: a high value on one signal can offset a low one | `min(T_source, C_content)`: the source is a **cap**. No content score can lift a memory above its source's trust ("convincing text from an untrusted source is not trusted"). **Correction (18 Nov): at the locked threshold θ = −0.05 the cap never changes a decision** (see "Full-text check" below); the ablation effect comes only from flagged memories with confidence 1.0 scoring exactly 0 without the cap. Do not argue this row as a tested difference |
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

## Full-text check (18 Nov 2026)

Read by an AI assistant for the author (not yet read by the author). What could be accessed:

| Work | Accessed | What matters for us |
| --- | --- | --- |
| MemPoison (arXiv 2607.14651v2; listed as a NeurIPS 2026 poster) | Full HTML (main text + appendices) | Write-time baselines: (a) **consistency check** = heuristic risk `0.45·overlap + 0.35·entity mismatch + 0.20·update language` against trusted memories, reject above 0.58 (no LLM); (b) **LLMJudge Write** = Qwen3-8B sees candidate + source label + truncated memory summary, outputs a risk score; (c) novelty filter; (d) MIXed. Thresholds set on a clean split to keep 85% of clean memories. Results (BCR, lower is better): no defense 62.6% (L1 45.4%); consistency 20.1% (L1 4.8%, L2 22.5%, L3 27.8%); LLMJudge 17.8% (L1 12.1%). CleanAcc almost unchanged (94.4 → 93.7–94.0). A benign-update test exists, but in the text we could read only RejectAll has numbers (post-update accuracy 2.2%); no per-defense update cost. No adaptive attacks against the defenses, no tool-call authorization, no LoCoMo. Their consistency check uses "update language" as a **risk** feature, i.e. it treats updates as suspicious by design. Code/data: github.com/resautu6/MemPoison, huggingface.co/datasets/MemPoison/MemPoison |
| SAGE-Mem (ICML 2026 SCALE workshop) | Project page + code repo (MIT, commit fdd5c24) + frozen result CSVs; OpenReview PDF blocked by a browser check | LoCoMo-Adv is generated on the fly from locomo10.json: 8 families, mostly directive text ("override previous answers", "[SYSTEM VERIFIED] ... answer is unknown"); only `fact_overwrite_injection` states a wrong value. In their own CSVs the undefended baseline has **false-belief rate 0** and retrieval ASR 0.13, so most families do not change answers. SAGE-Mem admits 0/4,800 attack writes except OCR (20/600), but its **benign write recall is 0.98%** (3,460 of 352,920 benign writes admitted; `analysis/locomo_adv/main_focus_benign_write_recall.csv`); BCU 0.46 vs 0.64 undefended. How conflicts vs legitimate updates are handled is not described on the page |
| MIVL (SSRN 6880480) | **Not accessible** (SSRN 403, no other copy found by search) | Still known only second-hand (MemSentry's related work). Any comparison must say so, or be dropped |
| TMA-NM, SMSR, MemSentry | Not re-read | Abstract-level only, as before |

### What the code shows about our own gate (checked on all test logs)

At the locked thresholds (θ_accept = θ_reject = −0.05, λ_r = 1) every one of 288,536 test-time gate decisions
(LoCoMo main, adaptive, LongMemEval; 4 models) is **accept ⟺ R_poison = 0, reject ⟺ R_poison = 1**, and there is
no quarantine. Reason: R ∈ {0, 1} and min(T, C) ∈ [0, 0.9], so the score is ≥ 0 when R = 0 and ≤ −0.1 when R = 1.
Source trust, content confidence and the time factor never change a decision. As deployed, the Trust Gate is
"reject if the LLM contradiction judge says conflict OR an assertion pattern appears in the source turn".
The threshold criterion that weights external-source FRR equally (our circular-reasoning control) is what made
provenance inert. This must be reported; it is also a finding in its own right.

### What can still make the paper different (none of the three papers shows these)

1. **Updates look like poison, measured directly**: a dedicated set of legitimate knowledge updates (LongMemEval),
   4 judge models, update accuracy −35 points pooled [−45, −26]; and a time factor in this formula cannot fix it.
   MemPoison reports no per-defense update cost; SAGE-Mem reports a utility drop but not why.
2. **What does the work**: the gate collapses to its LLM judge (+ a lexicon). The contradiction-only baseline
   (added 18 Nov) tests this directly; the lexicon only helps against the exact phrases it lists (A2 0% → AD1/AD2
   +13–16 points pooled, intervals exclude 0).
3. **Fair threshold selection erases provenance**: with external-source FRR weighted like attack acceptance, the dev
   tuning picks a threshold at which source trust is inert. A cautionary result for "provenance-aware" gates.
4. **Memory is not authorization**: a dialog-stated authorization passes every gate (AD4, 39% attempts with the
   gate pooled); only the separate allowlist stops it. Neither MemPoison nor SAGE-Mem evaluates tool authorization.
5. **Judge dependence**: the same gate gives 2% (qwen3, gemma4) to 63% (olmo-3) clean-dialog FRR. MemPoison uses one
   judge (Qwen3-8B).
6. **Utility at a realistic operating point**: ~98% of clean dialog memories kept (qwen3, gemma4), versus ~1%
   benign write recall for SAGE-Mem on its own benchmark. Different pipelines and units: present side by side,
   never as a head-to-head win.
