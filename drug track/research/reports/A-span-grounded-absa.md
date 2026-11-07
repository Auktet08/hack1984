# Research report A: span-grounded aspect-based sentiment (ABSA)

Run: 2026-11-07, `claude-A`. Plan: `research/plans/A-span-grounded-absa.md`. Research only: nothing was installed
or added to the pipeline. Raw files: `research/raw/{tavres,tav,tavext,exa,gh}-A-*.json`, merged list
`research/raw/A-merged.json` (111 unique URLs), schema `research/raw/A-candidate-schema.json`.

**Baseline context** (from `docs/experiments/log.md`): L3 rules 0.843 on dev (E009). 31 of 56 dev aspects missed,
mostly PubMed efficacy claims with no cue words. E018 simulation puts the break-even aspect precision at about
0.35 to 0.4, so a recall-oriented aspect detector pays even when it is noisy. E008: widening spans to whole clauses
hurt span F1. Self-consistency voting is already on the rejected list.

## Top picks

### 1. NLI cross-encoder as an implicit-aspect detector (form d, plus an a-style hypothesis set)

- **What:** score each sentence of a PubMed/news item against 2 to 4 hand-written hypotheses per aspect with an
  off-the-shelf NLI cross-encoder, for example "This sentence reports that the treatment improved outcomes"
  (efficacy) or "This sentence reports side effects or toxicity" (safety). Add an aspect where the best sentence
  passes a threshold and L3 has nothing. The best-scoring sentence also gives a span candidate, to be trimmed by
  the existing cue-span logic. Putting the product name in the hypothesis covers A5: polarity lands on the
  product the sentence is about.
- **Models (verified on the HF API and model cards):**
  `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` (184M params, MIT, binary entailment / not-entailment, HF
  `zero-shot-classification` pipeline with `hypothesis_template` and `multi_label=True`; the `-c` variants use
  only commercially clean training data). The CPU-fast alternative is `dleemiller/EttinX-nli-s` (68M, MIT,
  ModernBERT-based, distilled from `ModernCE-large-nli`, which is 395M and MNLI-mm 0.920).
- **Evidence:** Seoh et al. EMNLP 2021 (paper read via tavext-A-2) cast aspect sentiment as NLI ("The {aspect}
  is good/bad"). It reached about 77% accuracy on implicit aspect categories after training on 16 reviews, against
  65% for the no-prompt baseline. Yin et al. 2019 is the entailment zero-shot classification recipe, and
  auto-verbalizer work (Frontiers 2024) shows that expanding a category label into several phrasings helps
  zero-shot ACD. Caveat from Seoh: an MNLI-only model with no in-domain pretraining did poorly at full-shot, so
  biomedical wording is the main risk.
- **Target metric:** aspect recall (aspect F1), with a second effect on span F1 through sentence choice.
- **Expected effect:** if it recovers half the missed aspects at precision 0.8, E018 says about +0.025 composite.
  At precision 0.5, about +0.012. Both are below the ±0.055 dev noise, so judge it on aspect F1 and recall, not on
  the composite.
- **Effort:** about 2 to 3 h (load the model, write the hypothesis set from `LABELING_GUIDE.md`, sweep the
  threshold on dev).
- **Risks:** threshold overfit on 56 dev aspects; hypotheses fire on background sentences ("previous studies
  showed…"); latency of 5 aspects × N sentences × items (fine at 68 to 184M on CPU or GPU).
- **Experiment:** L3 + NLI aspects on PubMed only, added only where L3 has none, with a sweep of thresholds
  0.5/0.7/0.9 and of base vs EttinX-s. Log aspect P/R and span F1 as a new E-row.

### 2. Prompt recipe for Qwen3.5-2B: covering demonstrations, retrieval, no CoT, ordered output (form a)

- **What:**
  - (i) Choose few-shot demos so they cover every aspect × polarity combination. This is the RANLP 2025
    selection rule (paper read).
  - (ii) Or retrieve the k most similar labelled examples per input. This is the IT-RER-ABSA pattern (MIT,
    flan-t5-base, active 2026-03); its README warns that a demo with a misleading opinion word hurts.
  - (iii) No chain-of-thought.
  - (iv) Use human-readable aspect descriptions instead of bare codes, and emit tuples in text order. These are the
    GEN-SCL-NAT target-format changes.
  - (v) State in the instruction that aspects can be implicit (no aspect word in the text). This is what ITSCL's
    instruction does.
- **Evidence:**
  - RANLP 2025 (Ventirozos et al., read): for quad prediction, few-shot demos alone beat CoT prompting, and the
    best CoT order differs from aspect→opinion→polarity.
  - arXiv 2503.03064: CoT sharpens the score distribution and hurts pointwise scoring (no-CoT better in 14 of 16
    cases).
  - InstructABSA (NAACL 2024, MIT): definition + 2 positive + 2 negative + 2 neutral examples beats 7× larger
    models, and misleading examples cost about 10%.
  - GEN-SCL-NAT: +1.5 F1, with gains on the implicit splits.
- **Target metric:** aspect recall and span F1 for the LLM path.
- **Effort:** 1 to 2 h on top of whatever prompt exists.
- **Risks:** the demo pool is dev (leakage into the dev score) unless demos come from teacher-labelled unlabeled
  items. Use those, and keep dev for scoring. A long prompt costs 2B latency.
- **Experiment:** A/B on dev: current prompt vs (covering demos + no CoT + ordered output) vs (+ retrieved demos
  from teacher-labelled unlabeled items).

### 3. Expected-value polarity decoding from token logprobs (form a)

- **What:** at the polarity slot, read the 2B model's probabilities for the 5 polarity tokens (−2..+2),
  compute the expected value, and round it, or map it with thresholds tuned once on dev. Do this instead of greedy
  argmax.
- **Evidence:**
  - arXiv 2406.10267: expected value over option-token probabilities beats greedy on Likert-scale scoring
    (Mixtral SummEval Pearson 20–46% → 37–56%).
  - arXiv 2503.03064: the mean beats the mode in 42 of 48 settings, and removing CoT helps the mean more.
  - For trained encoder heads, AIME-Con 2026 (DeBERTa-v3-base, 5 levels, 99k items) gives a mixed picture: CORN
    mode QWK 0.594 ≈ classification 0.593 > CORAL-expected 0.576 > regression 0.561, and CORAL median does
    poorly. So an ordinal loss is not a clear win for an encoder, while expected-value decoding is the cheap win
    for an LLM. `coral-pytorch` (MIT, active 2025-09) has a DistilBERT+CORN 5-star tutorial if we ever train a
    head.
- **Target metric:** QWK (mostly ±1 vs ±2 errors). **Expected effect:** small, since QWK is on matched aspects
  only. It mainly hedges the QWK cliff (E010).
- **Effort:** about 1 h if the serving stack exposes top-k logprobs (vLLM and llama.cpp both do).
- **Risks:** rounding pulls toward 0 and ±1, and dev is too small to tune the thresholds reliably.
  Multi-token polarity strings need a single-token label alphabet (e.g. A..E) as in 2406.10267.
- **Experiment:** same predictions, greedy vs EV-rounded polarity, compare QWK on matched dev aspects.

### 4. LA-ABSA silver-label recipe for LoRA data (form c)

- **What:** the teacher labels the 1,733 unlabeled items with ICL (about 50 demonstrations). Drop any silver span
  that is not a verbatim substring (the DS2-ABSA label-refinement rule), then fine-tune the student on the
  result. This matches the decision in force that teacher labels on unlabeled items are allowed (§4.3).
- **Evidence:**
  - LA-ABSA (LREC 2026, paper read): Gemma-3-27B annotates, and a student under 1B params (T5-base class)
    trained on its labels reaches ASQP Rest16 F1 49.85, vs 51.10 for the teacher's own ICL.
  - EHSAN (healthcare ABSA): training on LLM-only labels loses under 0.02 F1 against fully human-reviewed labels,
    and fewer aspect classes helps.
  - Hellwig ESWA 2024: synthetic data helps most in the 25-example regime.
- **Caveat:** the LA-ABSA repo has **no license** and no install instructions ("TBA"), so we borrow the recipe,
  not the code.
- **Target metric:** all of aspect recall, QWK and span F1 through the LoRA'd 2B. **Effort:** over 3 h end to
  end, but the labelling step is presumably another workstream's job. The A-specific part is the
  verbatim-span filter plus the demo selection from pick 2 (about 1 h).
- **Risks:** teacher label noise on implicit aspects. R6 does not apply (no external data), but never include
  test items.

### 5. (maybe) Entity-conditioned polarity via a targeted-sentiment model (form d)

- `nicolay-r/flan-t5-tsa-thor-base` (248M, MIT, THOR CoT target sentiment, news-domain RuSentNE) or the
  `chahinMalek/sane` pattern (MIT: NER → per-entity ABSA, polarity = P(pos) − P(neg)). Use it only if items that
  name two products (e.g. a rival comparison) show polarity landing on the wrong product. The NLI-with-product
  hypothesis from pick 1 covers most of this for free. Effort 1 to 2 h. Low priority.

## Full candidate table

GH = GitHub API (`gh-A-repos.json`), HF = HF API (`gh-A-hf.json`). "Read" = README, card or paper fetched.

| Candidate | URL | Form | Size | License (verified) | Last activity | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| deberta-v3-base-zeroshot-v2.0 | huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0 | d | 184M | MIT (HF) | 2024-04 | **adopt** (pick 1) | read; offline; entailment zero-shot |
| EttinX-nli-s | huggingface.co/dleemiller/EttinX-nli-s | d | 68M | MIT (HF, card) | 2025-10 | **adopt** (pick 1 alt) | read; CPU-fast |
| deberta-v3-large-zeroshot-v2.0 | huggingface.co/MoritzLaurer/deberta-v3-large-zeroshot-v2.0 | d | 435M | MIT (HF) | 2024-04 | maybe | slower; try if base is weak |
| Seoh et al. 2021 NLI prompts | doi 10.18653/v1/2021.emnlp-main.509 | a | BERT-base | paper | 2021 | **adopt** (method) | read; implicit categories 77% vs 65% |
| RANLP 2025 ASQP ICL | aclanthology.org/2025.ranlp-1.152 | a | n/a | paper | 2025 | **adopt** (pick 2) | read; few-shot > CoT; covering demos |
| IT-RER-ABSA | github.com/zgMin/IT-RER-ABSA | a | flan-t5-base | MIT (GH) | 2026-03 | **adopt** (idea, pick 2) | read; retrieved demos |
| InstructABSA | github.com/kevinscaria/InstructABSA | a | Tk-Instruct 200M | MIT (GH, HF) | 2024-07 | maybe | prompt template only; checkpoints are restaurant/laptop aspect terms |
| GEN-SCL-NAT | github.com/jpeper/GEN_SCL_NAT | a | T5-large 770M | **none** (GH; Tavily said Apache-2.0, wrong) | 2024-03 | maybe (format only) | read; no license, so borrow only the format ideas |
| ITSCL | github.com/sydmou/ASQP-ITSCL | a | T5-base/large | MIT (GH) | 2025-01 | reject | needs training; implicit-instruction idea folded into pick 2 |
| JCDL 2026 implicit-aware ACOS study | doi 10.1145/3805696.3846476 | info | T5-base | paper | 2026 | info | when neither aspect nor opinion is written, nothing beats seed noise; supports an NLI/LLM route over seq2seq tweaks |
| Expected-value decoding | arxiv 2406.10267; 2503.03064 | a | n/a | papers (code: dubai03nsr/distributional-judge) | 2024–25 | **adopt** (pick 3) | highlights + abstracts; cheap |
| AIME-Con 2026 ordinal vs classification | aclanthology.org/2026.aimecon-main.55 | info | DeBERTa-v3-base | paper | 2026 | info | Exa highlight incl. table; ordinal heads ≈ classification |
| coral-pytorch | github.com/Raschka-research-group/coral-pytorch | d | n/a | MIT (GH) | 2025-09 | maybe | only if we train an encoder polarity head |
| LA-ABSA | github.com/NilsHellwig/LA-ABSA | c | <1B student | **none** (GH; Tavily said MIT, wrong) | 2026-02 | **adopt** (recipe, pick 4) | paper read; code unlicensed, no install docs |
| DS2-ABSA | arxiv 2412.14849 | c | n/a | paper | 2024 | adopt (one rule) | verbatim-span filter for silver labels |
| EHSAN | arxiv 2508.02574 | c | n/a | paper | 2025 | info | LLM-only labels lose < 0.02 F1 |
| Hellwig ESWA 2024 synthetic ABSA | doi 10.1016/j.eswa.2024.125514 | c | n/a | paper | 2024 | info | synthetic data helps mainly at about 25 examples |
| nchellwig-dimabsa (SCSG self-consistency) | github.com/NilsHellwig/nchellwig-dimabsa | a | Gemma-3 27B | none (GH) | 2026-03 | reject | self-consistency already rejected in log; 27B |
| SemEval-2026 DimABSA data/tasks | github.com/DimABSA/DimABSA2026 | c | n/a | none (GH) | 2026-06 | reject | restaurant/laptop VA scores; idea only: aspect-conditioned encoder regression is stable |
| THOR-ISA | github.com/scofield7419/THOR-ISA | a | Flan-T5 up to 11B | Apache-2.0 (GH) | 2023-08 | reject | 3-hop CoT; CoT hurts small-model scoring (2503.03064, RANLP 2025) |
| flan-t5-tsa-thor-base | huggingface.co/nicolay-r/flan-t5-tsa-thor-base | d | 248M | MIT (HF) | 2025-08 | maybe (pick 5) | Tavily report only; not read |
| sane (entity-level sentiment) | github.com/chahinMalek/sane | d | HF ABSA model | MIT (GH) | 2026-02 | maybe (pick 5) | pattern only |
| sentiner + deberta-v3-base-targsenti-v5 | github.com/thieled/sentiner | d | 184M | CC-BY-4.0 (repo); model no license (HF) | 2026-07 | reject | R package; model unlicensed |
| PyABSA | github.com/yangheng95/PyABSA | d | BERT/DeBERTa | MIT (GH) | 2026-11 | reject | active, but aspect-term models for reviews; no category/implicit fit |
| SetFit-ABSA restaurants | huggingface.co/tomaarsen/setfit-absa-bge-small-en-v1.5-restaurants-aspect | d | ~33M | Apache-2.0 (HF) | 2023-12 | reject | aspect terms in restaurants |
| NUSTM/ACOS, One-ASQP data, NEUDM/absa-quad | github.com/NUSTM/ACOS etc. | c | n/a | none on all three (GH/HF; Tavily claimed MIT for two, wrong) | 2021–23 | reject | restaurant/laptop; unlicensed |
| Qwen2.5-3B LoRA ABSA (MDPI 2026) | mdpi.com/2673-4591/128/1/15 | c | 3B | paper | 2026 | reject | weak result (64.5% acc), no code |
| Qwen1.5-1.8B QLoRA ACSA | github.com/SaltyGod/Qwen-Qlora-ACSA | c | 1.8B | not checked | n/a | info | shows a ≤2B QLoRA over a fixed category list works (86% acc, 18 categories) |
| Patient drug-review ABSA (DrugLib/drugs.com, SentiDrugs, DrugsReviewsCorpus, ATEdrug, OSF y4hx2 LLM labels) | see exa-A-5, exa-A-12 | b/c | n/a | DrugLib: research-only, no redistribution | 2018–26 | reject (maybe as verbalizer source) | patient-review register ≠ trial abstracts; OSF y4hx2's aspects (efficacy, safety, treatment burden, cost/access) match ours and could seed hypothesis wording; R6 dedupe if ever used |
| PubMed treatment-effects corpus (Nakov et al.) | arxiv 1912.01831 | c | n/a | unknown | 2019 | maybe | 750 abstracts with positive/negative/neutral effect + rationale sentence; availability unchecked; R6 dedupe required |
| UzMedSentiment | huggingface.co/datasets/uznlp-uz/UzMedSentiment | c | n/a | not checked | n/a | reject | Uzbek; schema twin (aspect, −2..+2, cue span) only |
| Finance entity sentiment (SEntFiN, FiQA, FinEntity, FinLin) | Tavily report 3 | c | n/a | Tavily-claimed, unverified | n/a | reject | domain mismatch; method is generic targeted sentiment |
| GAN-BioBERT trial-abstract sentiment | pmc PMC9170913 | d | BERT-base | n/a | 2022 | reject | document-level, not aspect-level |
| Therapy ABSA on Twitter | pmc PMC10558704 | c | n/a | tweet IDs only | 2023 | reject | text needs the X API |

## Themes that came back thin

- **A6 (biomedical ABSA):** nothing at aspect level for trial abstracts, press releases or regulatory text.
  Everything found is patient drug reviews (DrugLib, drugs.com, tweets) under research-only terms, or
  document-level trial-abstract sentiment. The nearest is the 750-abstract treatment-effects corpus (Nakov et al.),
  whose availability is unchecked. Takeaway: the domain data has to come from our own teacher labels (pick 4).
- **A4 (ordinal / QWK):** no ABSA paper optimises QWK on a −2..+2 scale. The evidence is borrowed from
  automated scoring and LLM-as-judge. The ordinal-loss result is mixed (ordinal ≈ classification), and
  expected-value decoding is the only consistently positive result.
- **A5 (entity-targeted):** the datasets are finance or news, and the reusable part is the input pattern (entity
  in the hypothesis or marker), not a model.
- **A1/A3 models:** plenty exist, but all are trained on restaurant/laptop categories, so they are useful only for
  output-format and prompt ideas.

Two of the five Tavily searches (ACOS implicit datasets, ordinal CORAL/QWK) returned only tokenizer/vocab files
from huggingface.co. The `--include-domains huggingface.co` filter with keyword-heavy queries did not work.

## Rule and cap notes

- **Tavily Research licenses were wrong 4 times** (GEN-SCL-NAT "Apache-2.0", LA-ABSA "MIT", NEUDM/absa-quad
  "MIT", One-ASQP "MIT"; the GitHub/HF APIs show no license on any of them). Target B saw the same thing. Its
  numbers (e.g. a "Flan-T5-250M RVISA 89.29 F1" row) are also unverified and not used here.
- `tvly research run --no-wait` was ignored by CLI 0.2.1 (it waited and returned the finished report). One
  `tvly extract` call with `--chunks-per-source` was rejected client-side (pydantic error) and not sent.
- R1 check passed: the 16 saved queries (`A-query-tavres-*.txt`, `.query` in `exa-A-*.json` and `tav-A-*.json`)
  contain no `item_id`, `source_id`, title or URL from the 240 rows of `data/test_inputs.full.jsonl`.
- R6: no external dataset is adopted. The "maybe" datasets above need the test dedupe before any use.

## Spend

| Tool | Calls | Credits / $ | Bucket | Cap |
|---|---|---|---|---|
| Tavily Research mini | 3 | unknown (4–110 each, 12–330 total); `/usage` needs an API key and we use OAuth | C | 3 runs: at cap |
| Tavily search basic | 5 | 5 | D | 5: at cap |
| Tavily extract basic | 2 × 5 URLs | 2 | D | ≤10: OK |
| Exa MCP search | 12 (10 planned + 2 thin-theme fills) | ≈ $0.084 (estimate, $0.007 each) | ad-hoc | ≤15: OK |
| Exa MCP fetch | 0 | $0 | ad-hoc | ≤10: OK |
| GitHub + HF REST API | 26 | free | none | — |

Ledger: 7 lines with `"who":"claude-A"` in `research/ledger.jsonl`.
