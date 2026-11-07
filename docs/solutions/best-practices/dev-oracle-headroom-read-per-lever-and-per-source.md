---
title: "Dev oracle headroom: 0.904 is the aspect-only ceiling, and PubMed holds most of the gap"
date: 2026-11-07
category: best-practices
module: drug track/scoring
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "Quoting an oracle result as the ceiling or the headroom for the whole system"
  - "Deciding whether score work is worth the time, or cutting it from a plan"
  - "Reading aspect recall on dev as a guide to free-text performance"
  - "Choosing which source or metric a model or rule change should target"
tags:
  - hack1984
  - scoring
  - oracle
  - headroom
  - aspect-recall
  - pubmed
  - span-f1
---

# Dev oracle headroom: 0.904 is the aspect-only ceiling, and PubMed holds most of the gap

## Context

The lean plan (decision 8 in `drug track/PROBLEM.md:55`, and `docs/ideation/2026-11-07-lean-plan.md:10`) cut score
work partly because "even perfect aspects reach only 0.904 (E017)" and "the headroom is small". E017 is real, but
it is an **oracle for one lever**: it gives L3 every missed aspect and leaves signal type and actionable as they are.
It was then read as the ceiling for the whole system. Two more oracle cuts and a recall breakdown, run on the same
dev set, change the picture.

## Guidance

1. **An oracle bounds only the fields it fills.** Composite is the plain mean of seven parts
   (`drug track/scoring/score.py:111-115`), so making one part perfect adds at most (1 − x)/7. E017 moves aspect F1
   from 0.617 to 1.0 (+0.055) but leaves signal macro-F1 at 0.856 and actionable F1 at 0.762. The per-lever oracles
   recorded with E017 are: aspects +0.061, spans on matched aspects +0.038, actionable +0.034, signal +0.020.
   Together they cover most of the gap from 0.843 to 1.0. Say "the aspect ceiling is 0.904", never "the ceiling is 0.904".
2. **Cut oracles by source as well as by metric.** Giving L3 the gold PubMed fields (E019) is worth more than any
   single-metric oracle:

   | Gold PubMed fields given to L3 | Dev composite | Gain |
   |---|---:|---:|
   | none (L3, E009) | 0.843 | — |
   | signal type only | 0.858 | +0.015 |
   | actionable only | 0.865 | +0.022 |
   | aspects only (gold polarity, speaker, exact span) | 0.920 | +0.077 |
   | all of them | 0.957 | +0.114 |

   PubMed is 26 of 60 dev items and 104 of 240 test items, about 43% of each.
3. **Exact spans are worth far more than nearby windows.** With gold spans on PubMed, span F1 goes from 0.731 to 0.953
   (E019). E017 used 12-word windows centred on the gold span and reached only 0.747. Span F1 is token overlap on
   matched aspects (`score.py:88-92`), so extra words cost on every aspect found. A short span pointed at the right
   place is a score lever, not just a citation detail.
4. **Dev aspect recall overstates free-text recall.** L3 matches 25 of 56 gold aspects (45%), but 10 of those 25 are
   fda_event aspects parsed from a structured `Reactions:` field (10 of 10 found). On free text it finds 15 of 46 (33%):
   PubMed 13/31, press releases 1/10, news 1/4, fda_label 0/1. Test is weighted toward the weak sources (pubmed 104,
   news 30, press 18 vs fda_event 37), so expect test aspect recall below the dev figure.
5. **Separate "can dev confirm it" from "is it worth it".** The ±0.055 dev noise means dev cannot confirm a +0.025 gain.
   It does not mean the gain is absent on test. E018's simulated 2B model (half the missed aspects at precision 0.8)
   averaged +0.025 over 40 seeds, with break-even precision about 0.35–0.4. That is an expected gain, and it is the
   reason to gate the model at G1 rather than drop it.

## Why This Matters

Reading E017 as a whole-system ceiling made score work look nearly exhausted and pushed the PubMed model path behind
transcripts. The source cut shows PubMed holds the single largest lever (+0.114 upper bound), and the same model path
serves both PubMed aspects and transcripts. A plan built on the wrong ceiling under-invests in the largest lever it has.

## When to Apply

- Before writing "the ceiling is X" or "the headroom is small" in a plan, a decision or a pitch: name which fields
  the oracle filled.
- Before cutting a lever for being "below noise": check its oracle by source, not just by metric.
- When comparing aspect recall across splits: report it with and without fda_event.

## Examples

Recall by source for L3 on dev (`drug track/out/dev/dev_L3.jsonl` against `drug track/data/dev.full.jsonl`, both
gitignored):

| Source | Gold aspects | L3 finds | Recall |
|---|---:|---:|---:|
| fda_event | 10 | 10 | 100% |
| pubmed | 31 | 13 | 42% |
| press_release | 10 | 1 | 10% |
| news | 4 | 1 | 25% |
| fda_label | 1 | 0 | 0% |
| without fda_event | 46 | 15 | 33% |

Typical misses are mild claims in plain wording ("a high risk of venous thromboembolism (VTE) was observed",
"this regimen has demonstrated clinical efficacy"). 15 of the 31 misses are +1 and 9 are −1.

To reproduce a source oracle: copy L3's predictions, overwrite the chosen fields with gold for items of one source,
and score with `score.py --gold data/dev.jsonl --pred <file> --items data/dev.full.jsonl`. Log it as an `info` row.

Related: `composite-scorer-qwk-cliff-and-matched-only-metrics.md` (how the matched-only metrics work). Log rows
E009, E017, E018 and E019 in `docs/experiments/log.md`.
