---
title: "Judge changes on the silver holdout and OOF pool, not dev; use the local LLM as a scorer, not a generator"
module: drug track/src/v2
date: 2026-11-08
problem_type: best_practice
component: modeling
severity: high
applies_when:
  - "A change looks neutral on dev but you suspect test looks different"
  - "Choosing thresholds or policies for aspects, actionable or signal"
  - "Deciding how to use the 2B local model (generate JSON vs score options)"
tags: [hack1984, evaluation, silver, overfitting, qwen, polarity, spans]
---

# Judge on the silver holdout and OOF pool; use the local LLM as a scorer

## Context

Rules L3 scored 0.843 on dev but only 0.623 on the 105-item silver holdout, which is test-like (PubMed, news and press releases). On the holdout, aspect F1 was 0.22 and signal macro-F1 0.33, against 0.62 and 0.86 on dev. Its rules were written while reading dev answers, so dev hides how badly they transfer.

## Guidance

1. **Evaluate every change on three sets.** Use 5-fold out-of-fold predictions on the 925-item silver pool for tuning (`src/v2/cv.py`, `tune.py`), the silver holdout for confirmation, and dev as the gold check. Adopt a change only when they agree, or when the test-like sets agree and dev is within noise.
2. **Ask the 2B model to score fixed options, not to write JSON.** Read logprobs for "A–E" or "yes/no" and calibrate them with a small logistic layer on teacher labels:
   - The 5-point polarity rating reaches about 81% exact and QWK 0.84–0.86 on teacher quotes.
   - Rate the **whole chosen sentence**, not the short quote: holdout QWK 0.60 → 0.67.
   - Round the **expected value**. It minimizes squared error, which is what QWK rewards: pool QWK 0.761 vs 0.741 for argmax.
   - Item-level yes/no for safety presence reaches AUC 0.95–0.99.
   - Multiple-choice sentence location and sentence-level yes/no did **not** beat embedding logistic regression.
3. **Quote length matters.** Gold quotes are about 7–8 words. A ridge quote scorer on embeddings alone picked whole sentences (span F1 0.48 in the right sentence). Adding TF-IDF cue features and a small length penalty raised it to 0.59–0.64. Strip abstract headers such as "CONCLUSIONS:" from quotes.
4. **LoRA on this Mac is slow for long inputs.** It runs about 7.5 s/step at 900 tokens with 8 layers. A weak specialist (4 layers, rank 8, 300 steps) can show low validation loss while the answer-token distribution stays flat, because the loss averages over template tokens. Always check answer-token accuracy directly.

## Examples

| Change | Holdout | Dev |
|---|---:|---:|
| v1 hybrid (L3 + LoRA signal) | 0.633 | 0.846 |
| + embedding aspect heads and L4 rules (E057) | 0.657 | 0.855 |
| + LLM polarity, lexical quote scorer, actionable 0.3 (E058) | 0.678 | 0.867 |
| + zero-shot news/press signal (E059) | 0.695 | 0.868 |
| + cue and label rules, expected polarity (E060) | 0.709 | 0.864 |
| + stacked LLM safety presence (E062, released) | 0.710 | 0.865 |
