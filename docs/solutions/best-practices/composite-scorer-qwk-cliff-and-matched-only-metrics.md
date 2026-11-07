---
title: "Track 1 composite scorer: the QWK cliff, matched-only metrics, and why zero aspects is catastrophic"
module: drug track/scoring
date: 2026-11-07
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "Tuning which aspects to emit, or setting an aspect confidence threshold"
  - "Every matched aspect would carry the same polarity (e.g. a rules-only system whose only aspects are fda_event safety -1)"
  - "Deciding whether to abstain on uncertain items"
  - "Reading a dev composite where polarity_qwk, speaker_accuracy or span_f1 show 1.0"
tags:
  - hack1984
  - scoring
  - qwk
  - composite-metric
  - aspect-precision
  - abstention
---

# Track 1 composite scorer: the QWK cliff, matched-only metrics, and why zero aspects is catastrophic

## Context

The Track 1 leaderboard ranks on `composite`, the plain mean of seven parts (`drug track/scoring/score.py:111-115`): signal macro-F1, actionable F1, aspect F1, polarity QWK, speaker accuracy, span F1 and citation validity. A first rules-only system showed polarity QWK, speaker and citation all at 1.0 on dev. That looks like solved metrics, but it is an artifact of how the scorer computes them. Three behaviours drive this, and each is easy to miss when reading the README's metric table.

## Guidance

1. **QWK returns 1.0 when there is no variation, and drops to 0 with one disagreement.** `qwk()` returns `1.0 if pe == 0` (`score.py:48`). When every matched gold and predicted polarity is the same value (for example all fda_event safety −1), expected agreement is 0 and QWK is a perfect 1.0. Change one gold label to anything else and QWK becomes 0.0. On dev, that took the composite from 0.844 to 0.701 (−0.143, exactly one seventh). **Hedge** by making sure the matched aspects carry a few confident non-(−1) polarities. Eleven cue-word PubMed aspects held QWK at 0.961 and the composite at 0.860 under the same deviant label.
2. **Four of the seven parts only look at aspects you matched or predicted.** Polarity, speaker and span are computed only where gold and prediction both have the aspect (`score.py:88-96`). Citation validity is computed only over your own predicted spans (`score.py:108`). A missed aspect costs only aspect F1. A wrong extra aspect can hurt up to four parts. So **set emit thresholds against the composite, not aspect F1**, and favour precision.
3. **Never submit zero aspects.** With no matched aspects, QWK, speaker and span become `None` and count as 0 in the composite (`score.py:95-96, 111`). Citation validity is `None` and drops out of the average (`score.py:113`). Keeping the same signal and actionable predictions but removing all aspects scored **0.167** on dev, against 0.731 with fda_event aspects. An "abstain when unsure" system that abstains everywhere is close to the worst possible submission.
4. **Signal macro-F1 only averages the classes present in gold** (`score.py:73`). Each rare class (guideline, access_pricing, competitor_move, expert_opinion) is worth about 1/9 of that metric, roughly 1.6 composite points, however few items it has.

## Why This Matters

The cliff is a 0.14 tail risk that sits on a mostly model-drafted gold set: only 15 of 60 dev items were human-reviewed. A rules-only entry whose matched polarities are all −1 is betting that every one of 37 test fda_event labels is exactly −1. The matched-only denominators also mean 1.0 scores on dev say nothing about quality once a model starts adding aspects. That is why "fill in every aspect" LLM pipelines can score below precise rules.

## When to Apply

- Any change that adds, removes or thresholds aspects. Log it in `docs/experiments/log.md` (rows E002, E010 and E011 record these measurements).
- Before submitting: check that matched polarities are not all one value, and that at least some aspects are predicted.
- When a dev table shows QWK, speaker or citation at 1.0, check how many aspects were matched (`n_aspects_matched`) before trusting it.

## Examples

Measured on dev with `score.py --items data/dev.full.jsonl`:

| Setup | Composite | Note |
|---|---|---|
| Rules v2, matched aspects all fda_event −1 | 0.844 | QWK 1.0 |
| Same, one gold fda_event polarity changed to 0 | 0.701 | QWK 0.0 (cliff) |
| Same deviant gold, plus 11 cue-word PubMed aspects (+2/+1/0/−1) | 0.860 | QWK 0.961 (hedged) |
| Rules v1 signal/actionable, all aspects removed | 0.167 | QWK, speaker, span count as 0 |
| Current `src/rules/predict.py --level 3` | 0.843 | QWK 0.933, no longer all −1 |
