# DATA.md: what we were given, measured

This file covers the data and the scorer, and what they mean for choosing models and strategies.
The rules come from `README.md` and `LABELING_GUIDE.md`, and the plan is in `PROBLEM.md`.
Every number here was measured on 2026-11-07 with `analysis/profile.py` and `analysis/baseline.py`:

```bash
python3 -I analysis/profile.py  "$PWD"   # split, source, label and span statistics
python3 -I analysis/baseline.py "$PWD"   # rule baselines and ceilings scored with scoring/score.py
```

Test items were profiled on **input fields only** (source, reporter, status, length). No test item was
labeled, searched or read for its answer.

---

## 1. The task in one paragraph

Each item is one public document about two EGFR-mutated NSCLC franchises: **A** = Tagrisso (osimertinib),
**B** = Rybrevant / Rybrevant Faspro (amivantamab) + Lazcluze (lazertinib). For each item we output:

- `signal_type` (9 classes)
- `actionable` (yes/no)
- five aspects: `efficacy`, `safety`, `convenience`, `access_cost` and `evidence_quality`. Each is `null`, or
  `{polarity −2..+2, speaker, span}`, where `span` is a verbatim quote from the text.

Inference must run offline on a self-hosted model (3B class per `PROBLEM.md`).

---

## 2. The files

| File | Items | Labels | Use |
|---|---:|---|---|
| `data/dev.full.jsonl` | 60 | gold (15 `human_reviewed`, 45 drafted by a frontier model, then reviewed) | tune, eval, few-shot |
| `data/test_inputs.full.jsonl` | 240 | none | the submission |
| `data/unlabeled.full.jsonl` | 1,733 | none | silver labels, distillation, retrieval, trend demo |
| `data/*.jsonl` (no `.full`) | same | same | PubMed `text` is `null`. **Always use the `.full` files.** |

PubMed abstracts are already rehydrated: no item in any `.full` file has null text.

Item fields: `item_id`, `source`, `source_id`, `url`, `published` (YYYY-MM-DD), `product` (A/B/both), `title`,
`text`, `text_sha256`. Dev adds the label fields plus `human_reviewed`.

### 2.1 Source mix per split

| Source | Dev | Test | Unlabeled | Test share |
|---|---:|---:|---:|---:|
| pubmed | 26 | 104 | 896 | 43% |
| ctgov | 10 | 40 | 142 | 17% |
| fda_event | 10 | 37 | 553 | 15% |
| news | 5 | **30** | 96 | 13% |
| press_release | 7 | 18 | 38 | 8% |
| fda_label | 2 | **10** | 8 | 4% |
| fda_notice | **0** | 1 | 0 | <1% |

**Dev does not look like test.** News is 12.5% of test against 8.3% of dev (1.5× the share), fda_label is 4.2% against 3.3%, and dev has
no fda_notice at all. News and fda_label are the sources where dev gives us the fewest examples, so weight per-source dev
scores toward the test mix.

ID prefixes: `PM` = pubmed, `CT` = ctgov, `FDA` = fda_event + fda_label + fda_notice, `NW` = news +
press_release, `U-` = unlabeled.

### 2.2 Products and dates

| | A | B | both |
|---|---:|---:|---:|
| dev | 31 | 22 | 7 |
| test | 117 | 92 | 31 |
| unlabeled | **1,266 (73%)** | 379 | 88 |

Unlabeled data leans heavily toward Tagrisso. A model trained on silver labels from it will see few B examples, so
upweight B or `both` when building fine-tuning sets. All splits cover 2025-01 to 2026-10 (test: 134 items in 2025, 106 in 2026).

### 2.3 Text length (words, median and range)

| Source | Dev | Test | Notes |
|---|---|---|---|
| fda_event | 19 (10–33) | 14 (11–56) | one templated sentence |
| ctgov | 60 (47–95) | 56 (40–93) | templated registry summary |
| fda_label | 112 (107–118) | 82 (34–124) | "New text … Removed text …" diff, cut with "…" |
| news | 111 (106–119) | 112 (24–137) | headline + snippet, pieces joined by `[...]` |
| pubmed | 243 (59–468) | 243 (66–451) | abstract. 56/104 test abstracts have `RESULTS:`/`CONCLUSIONS:` headers |
| press_release | 1,200 (1,075–1,200) | 1,200 (587–1,200) | **cut at 1,200 words.** 53/56 test+unlabeled hit the cap. Starts with site navigation boilerplate |
| fda_notice | none | 604 | FDA.gov page incl. boilerplate |

Press releases are the longest items at about 1,600–1,800 tokens. Every item plus a prompt of about 2k tokens fits in a 4k context, but a long few-shot prompt needs 8k.

---

## 3. Anatomy of each source, and how gold treats it

### 3.1 ctgov (test 40): almost fully rule-driven

```
NCT04233021 · PHASE2 · Sponsor: …. <title>. Status as of last update (2025-02-03): COMPLETED.
(No earlier snapshot to compare.) Interventions: …. Primary outcome: …. Results posted: no.
```

Two templates:
- **Status snapshot**: `Status as of last update (date): STATUS.` Test: COMPLETED 11, RECRUITING 6, ACTIVE_NOT_RECRUITING 5,
  TERMINATED 1, APPROVED_FOR_MARKETING 1.
- **New registration**: `New registration first posted on <date>. Status: NOT_YET_RECRUITING.` 16 in test. Many are
  **rival drugs with osimertinib as comparator or backbone** (glumetinib, limertinib, etc.).
- Terminations carry `Reason given: "…"`. All four seen in test and unlabeled are business or enrollment reasons, so no aspect applies.

Gold (dev, 10/10): `trial_update`, actionable `no`, all aspects null. The guide says new **phase 3** registrations
and terminations of our products' trials should be `yes`. Dev has no examples of either, so this rule is untested.
Test has 3 phase 3 records (`PHASE3` ×2, `PHASE2, PHASE3` ×1).

### 3.2 fda_event (test 37): rule-driven, but the span is noisy

```
Suspect product: amivantamab. Reactions: Rash, Ocular toxicity. Serious: yes; outcome: other serious. Reporter: physician.
```

Gold (dev, 10/10): `safety`, `no`, safety −1, speaker `hcp` (physician / pharmacist / other health
professional) or `patient` (consumer). Test reporters: physician 15, consumer 11, other HP 8, pharmacist 3.

Special reactions in test+unlabeled: off label use 25, product use issue 1, no adverse event 1 (→ ignore);
malignant neoplasm progression 21, disease progression 11, drug ineffective 8 (→ efficacy −1);
inability to afford / product unavailable 0. Top real reactions: death 78, infusion related reaction 60, rash 53.

**Span inconsistency.** 53% of reports list several reactions. Gold sometimes copies the whole list,
sometimes only the first few ("Cardiac arrest" out of 9 reactions), and drops special reactions. Measured span F1 against dev gold:

| Span strategy | span_f1 on dev fda_event |
|---|---:|
| first reaction only | 0.53 |
| full list minus special reactions | 0.81 |
| **first 3 reactions (contiguous)** | **0.82** |

Tokens are compared whitespace-split, so `"Death,"` (trailing comma) and `"Death"` don't match. Copy the
comma-joined run exactly as it appears.

### 3.3 fda_notice (test 1): one rule

Gold per guide: `regulatory`, `yes`, efficacy +1, speaker `regulator`. The one test item is an FDA approval of a new
subcutaneous formulation, so ruling 9 applies: efficacy 0, safety 0, and convenience where the text says so.

### 3.4 fda_label (test 10): rules plus a judgement call

Title is `<Brand> label change: <Section>`. Test sections: Adverse Reactions 4, Warnings and Precautions 3, Dosage and
Administration 3. Text is a "New text … Removed text …" diff, cut short with "…".

Gold: a cosmetic table edit → `none`, `no`, all null. A Faspro q4w switch option → `regulatory`, `yes`,
convenience +1 regulator. The model must tell **clinically meaningful** changes from cosmetic ones (guide: new
indication → efficacy +1; boxed warning → safety −2; added warning or monitoring → safety −1; dosing burden → convenience).
Only 2 dev examples and 10 test items. Spans must not cross "…" (ruling 10).

### 3.5 press_release (test 18): speaker fixed, signal varies

Speaker is always `company`. Dev signals: efficacy 3, competitor_move 1 (J&J quarterly results), none 1
(AstraZeneca release about other cancers), regulatory 1, access_pricing 1 (Australian PBS listing). 5 of 7 are actionable.

Watch for:
- **Earnings releases** → competitor_move, actionable no, no aspects (ruling 5). Test has 3 by title (J&J Q3 2025, Q4/FY 2025, Q2 2026).
- **Boilerplate**: text often opens with site navigation ("Learn about our healthcare areas…") and ends with safety
  information. The useful claims are in the title and the first paragraphs. Gold spans come from the headline area.
- One span can serve two aspects ("an effective, safe and convenient treatment" → safety +1 and convenience +1).
- Polarity skews strongly positive: +2 for "statistically significant and clinically meaningful", "unmatched", "longest ever reported".

### 3.6 news (test 30): the hardest source per item

Headline plus snippet only, often several fragments joined by `[...]` (68/126 test+unlabeled). Gold speaker
in dev is `media` 4/4, because the writer frames the claim. The guide says to use `hcp`, `payer`, `regulator` and so on when someone
is quoted, but only 10/126 news items contain "said" and 15 contain "Dr." or "MD". Dev signals: efficacy 3,
guideline 1 (ASCO update), none 1 (explainer). Expect competitor_move and access_pricing here in test. Dev has
no news examples of them.

### 3.7 pubmed (test 104): the bulk of the model's work

Abstract text, structured with headers about half the time. Dev (26): efficacy 15, safety 6, none 4,
expert_opinion 1. Only **4/26 actionable**. Speaker always `researcher`.

Where gold spans come from (31 pubmed spans): no-header abstracts 11, RESULTS 7, CONCLUSION(S) 8, METHODS 3,
other 2. Positions are spread across the abstract, not only at the end. Typical patterns:
- `evidence_quality −1` for author caveats or design ("retrospective cohort study", "small sample").
- `efficacy 0` for "comparable OS"; ±1 for mild claims; +2 only for strong cue words.
- Preclinical and lab studies → efficacy, actionable no (ruling 2). PK or modelling studies → none or expert_opinion.

---

## 4. Gold label distributions (dev, n=60)

**signal_type × source**

| | efficacy | safety | trial_update | none | regulatory | competitor_move | guideline | access_pricing | expert_opinion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pubmed | 15 | 6 | | 4 | | | | | 1 |
| ctgov | | | 10 | | | | | | |
| fda_event | | 10 | | | | | | | |
| press_release | 3 | | | 1 | 1 | 1 | | 1 | |
| news | 3 | | | 1 | | | 1 | | |
| fda_label | | | | 1 | 1 | | | | |
| **total** | 21 | 16 | 10 | 7 | 2 | 1 | 1 | 1 | 1 |

**actionable**: 12 yes / 48 no. By source: press_release 5/7, news 2/5, fda_label 1/2, pubmed 4/26, ctgov 0/10, fda_event 0/10.
By signal: regulatory 2/2, guideline 1/1, access_pricing 1/1, efficacy 6/21, safety 2/16, the others 0.

**Aspects per item**: 0 → 23 items, 1 → 21, 2 → 13, 3 → 3. **38% of items have no aspect at all.**

**Aspect counts and polarity**

| Aspect | n | −2 | −1 | 0 | +1 | +2 |
|---|---:|---:|---:|---:|---:|---:|
| efficacy | 22 | | 3 | 2 | 9 | 8 |
| safety | 22 | | 16 | 1 | 5 | |
| evidence_quality | 8 | | 6 | 1 | 1 | |
| convenience | 3 | | | | 2 | 1 |
| access_cost | 1 | | | | 1 | |

No −2 anywhere in dev. Safety skews −1 (10 of those 16 are fda_event). Efficacy skews positive.

**Speaker by source**: pubmed → researcher 31/31; press_release → company 10/10; fda_event → hcp 7 / patient 3;
news → media 4/4; fda_label → regulator 1/1. **In dev, speaker is fully determined by source and reporter.**

**Spans** (56): median 8 words (1–20, mean 7.7); 56/56 verbatim; none end in punctuation; 2 items reuse one span
for two aspects.

---

## 5. How the scorer behaves (read before optimising)

Composite = mean of 7 metrics: `signal_macro_f1`, `actionable_f1`, `aspect_f1`, `max(polarity_qwk, 0)`,
`speaker_accuracy`, `span_f1`, `citation_validity`. Several properties of `scoring/score.py` matter more than
they first appear:

1. **Polarity, speaker and span are scored only on *matched* aspects.** Gold and pred both non-null on the same
   aspect. A wrong aspect you didn't predict costs only `aspect_f1` recall. A wrong aspect you did predict also costs
   `aspect_f1` precision, but it can't hurt the other three unless it matches gold. **A low-recall, high-precision
   aspect predictor still scores well on 3 of the 7 metrics.** This is the most important lever.
2. **QWK is knife-edge on uniform gold.** If every matched gold polarity is the same value (e.g. all −1 from
   fda_event) and every prediction equals it, QWK = 1.0. One different prediction drops it to **0.0**,
   because po = pe whenever gold is constant. With varied gold polarities it behaves normally. Practical
   consequence: never predict an aspect whose polarity you can't get right, and check QWK on dev before and after
   adding each new aspect source.
3. **span_f1** is bag-of-words F1 with lowercase and whitespace split. **Punctuation stays attached** (`"OS."` ≠ `"OS"`).
   Shorter spans that keep the cue words win. A span that runs into a trailing period loses a token.
4. **citation_validity** checks `span in text` exactly (case-sensitive). Enforce it in code. If no aspect is predicted
   at all, the metric is `None` and the composite averages over 6 metrics instead of 7.
5. **signal_macro_f1 only averages classes present in gold.** In dev all 9 classes appear, so each singleton class
   (competitor_move, guideline, access_pricing, expert_opinion) is worth 1/9 of the metric, about 1.6 composite points.
   Predicting a class that is absent from gold costs nothing beyond the item you got wrong.
6. **actionable_f1** is F1 on "yes" only. Predicting all "no" scores 0.
7. Missing items count as `none` / `no` / all-null. A polarity outside −2..2 **crashes** the scorer (KeyError):
   clip it.
8. The scorer also reports a `human_reviewed_only` block (15 items). It is a cleaner but tiny check set.

---

## 6. Measured baselines on dev (no model)

| Run | signal F1 | action F1 | aspect F1 | QWK | speaker | span | cite | **composite** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 `sample_submission` (all none) | 0.02 | 0 | 0 | – | – | – | – | **0.004** |
| B1 rules for ctgov/fda_event/fda_label only | 0.28 | 0 | 0.30 | 1.0 | 1.0 | 0.81 | 1.0 | **0.628** |
| B1 with fda_event span = first 3 reactions | 0.28 | 0 | 0.30 | 1.0 | 1.0 | 0.82 | 1.0 | **0.630** |
| B2 = B1 + pubmed/news/PR → `efficacy`, PR → actionable yes | 0.33 | 0.53 | 0.30 | 1.0 | 1.0 | 0.81 | 1.0 | **0.710** |
| O1 gold on ctgov/fda_event only | 0.23 | 0 | 0.30 | 1.0 | 1.0 | 1.0 | 1.0 | 0.648 |
| O2 gold everywhere | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1.000 |

How to read this:

- **Rules alone score 0.63–0.71.** Most of that comes from point 1 and point 2 in §5. The only aspects predicted are fda_event
  safety −1, so QWK, speaker and span look near-perfect. That will not hold once the model adds pubmed and news aspects.
- The remaining headroom sits in **signal_macro_f1 (0.33), actionable_f1 (0.53) and aspect_f1 (0.30)**, the three
  metrics the model must earn. Adding aspects raises aspect_f1, but every added aspect puts QWK, speaker and span at risk.
- Dev composite at this level is noisy. One item changes macro F1 by up to 1/9 per class. Report the `human_reviewed_only` score too.

---

## 7. What this means for models and strategy

### 7.1 Where the points are, ranked

| # | Lever | Metric(s) | Why |
|---|---|---|---|
| 1 | Source rules for ctgov, fda_event, fda_notice (78 test items, 33%) | all | Deterministic per the guide. Already worth 0.63 on dev |
| 2 | Span snapper: exact substring, one sentence, trimmed, no trailing punctuation | citation, span | Free 1/7 of composite, plus span_f1 |
| 3 | **Precision-first aspect gate**: predict an aspect only when the text judges our product and the polarity is confident | aspect_f1, QWK, speaker, span | Point 1 in §5. Tune the threshold on dev composite, not aspect_f1 alone |
| 4 | Signal classifier with strong rare-class recall: competitor_move, guideline, access_pricing, regulatory, expert_opinion | signal_macro_f1 | Each rare class weighs as much as efficacy. Use keyword cues (NICE/HAS/PBS/CDA/payer → access_pricing; NCCN/ESMO/ASCO guideline → guideline; FDA/EMA/CHMP action → regulatory; earnings or a rival-led item → competitor_move) plus augmented examples |
| 5 | Actionable rules + model | actionable_f1 | Strong priors: regulatory, guideline, access_pricing → yes; ctgov/fda_event → no unless phase 3 registration or our-trial termination; PR about our own pivotal data → yes; pubmed → no unless pivotal phase 3 |
| 6 | Polarity guards | QWK | Default to milder; ±2 only with strong cue words; "no new safety signals" → 0; "manageable"/"well tolerated" → +1 |
| 7 | Speaker by source | speaker | Determined by source in dev. Only news needs a quote-attribution check, and the default there is `media` |

### 7.2 Model options to evaluate

| Option | Fits | Notes |
|---|---|---|
| **Rules only** | ctgov, fda_event, fda_notice, fda_label skeleton, PR earnings | Baseline 0.63–0.71. Build first, keep as a fallback |
| **Small encoder classifiers** (e.g. DeBERTa-v3-base / ModernBERT, about 100–400M) for `signal_type`, `actionable`, aspect presence | pubmed, news, PR | Cheap, fast, calibrated probabilities make the precision gate easy. Needs silver labels (1,733 unlabeled) since dev has 60 |
| **3B instruct LLM + JSON-schema constrained decoding** (Qwen2.5-3B, Llama-3.2-3B, SmolLM3-3B; check what is current) | spans, polarity, news speaker, fda_label judgement | Generates spans and handles reasoning. Zero-shot first, then LoRA on silver + gold |
| **Hybrid** (recommended): rules → encoder heads for classification → 3B LLM only for aspect span + polarity on items the gate passes | all | Fewest LLM calls → best cost per 100 items; each part tunable separately |
| **Extractive span model** (token tagging over sentences) | spans | Guarantees verbatim spans. Alternative to the LLM + snapper |
| **kNN / retrieval few-shot** from dev + silver unlabeled, same source | LLM prompt | Same-source exemplars teach the gold span style. Cheap to add |

### 7.3 Training data plan implied by the numbers

- **Silver labels**: label all 1,733 unlabeled items with a frontier teacher prompted with the full guide. Calibrate it on dev
  first (target: the teacher reproduces dev gold, especially the 15 human-reviewed items). Gold for 45/60 dev items was itself
  drafted by a frontier model under the same guide, so a good teacher should track gold closely.
- **Rebalance**: unlabeled is 52% pubmed + 32% fda_event and 73% product A. Downsample fda_event (rules handle it), upweight
  news, press_release, fda_label and product B.
- **Rare classes**: dev has 1 example each of competitor_move, guideline, access_pricing and expert_opinion. Build an
  augmentation corpus (`RESEARCH_README.md` §5B) and dedupe it against test.
- **Hold-out**: keep 20% of silver as a second eval set. 60 dev items are too few to tune many thresholds on.

### 7.4 Experiments to run first (cheap → expensive)

1. Rules + B2 defaults + snapper → confirm 0.71, record it in `EVAL.md`.
2. Add keyword rare-class cues and actionable priors → measure macro F1 and actionable F1.
3. Zero-shot 3B LLM for pubmed/news/PR aspects, with a precision gate sweep (confidence threshold or "only if cue word") →
   plot composite against the threshold.
4. Teacher silver labels → encoder heads and/or LoRA 3B → compare with step 3.
5. Self-consistency (×3) on polarity only if QWK is the bottleneck.

---

## 8. Data quirks and risks

- **Dev is tiny and skewed.** 60 items, 9 classes, 4 singletons. Per-class F1 swings by 1.0 on one item. Don't
  over-tune on it.
- **Gold is partly model-drafted** (45/60). Expect some inconsistency, as in fda_event span length (§3.2).
- **Exact duplicates** exist only among short fda_event reports (9 test texts also appear in unlabeled, 1 in dev). Titles
  repeat across fda_label versions of the same section. No pubmed, news or ctgov duplicates by `source_id`.
- **Press release noise**: navigation boilerplate up front, 1,200-word truncation, and long safety boilerplate at the end.
  Strip boilerplate before prompting, but keep original offsets for spans.
- **News `[...]` and fda_label `…` joins**: never let a span cross them.
- **Rival-led items**: ctgov registrations and news where osimertinib is only a comparator or backbone. Signal is
  competitor_move (rival beats or challenges ours) or none. Efficacy for our drug is −1 only when the text says the rival beat it.
- **Private transcripts** (judged separately) are not in this data. Speaker turns will need their own speaker mapping.
