# Target B: clinical-claim polarity, open-source strategies

Run on 2026-11-07, following `~/.claude/plans/lets-look-for-specifically-twinkly-duckling.md`. This is research
only: nothing was installed or scored. Raw responses are in `research/raw/*-B-*`, and every call is in
`research/ledger.jsonl`.

**The question:** which open-source work can help a ≤3B, offline pipeline decide what a trial abstract's result says
(direction, favourability, firmness) and point to the evidence sentence? That decision is behind most of the 31
missed dev aspects (PubMed efficacy claims with no cue word).

## Bottom line

No off-the-shelf model drops in. The best Evidence Inference model (Fiorillo v0.5) is 4B parameters, needs a full
article plus an (intervention, comparator, outcome) prompt, and returns no span. What does transfer is a **way to
break the problem down**, which the literature has used consistently since 2004:

> polarity = **direction of change** (increased / decreased / no significant difference)
> × **whether the outcome is good or bad** (OS up is good; toxicity up is bad)
> × **whose arm is ours** (our product as the intervention, or as the comparator)
> then **intensity** from significance and hedging (guide: "significantly prolonged" = +2; when unsure, pick milder).

The small model (or a rule) only has to read the direction and the evidence sentence. Code computes the sign and
the strength. That suits a 2B model and the scorer: a sign worked out in code is consistent, and consistent
polarities protect QWK.

## Top picks

| # | Strategy | Form | Feeds | Effort | Source (verified) |
|---|---|---|---|---|---|
| 1 | Change × good/bad lexicon rule for PubMed efficacy and safety polarity | rule / lexicon | efficacy and safety recall, polarity sign | 1.5–2 h | Niu et al. 2005/2006 (method only, no released lexicon) |
| 2 | Evidence-Inference prompt for the 2B: read intervention, comparator, outcome, direction and sentence number; code maps them to polarity | prompt + guard | efficacy recall, QWK, span via sentence pointer | 2–3 h | Lehman 2019 / DeYoung 2020 task; Wadhwa 2023 framing; `bigbio/evidence_inference` (MIT annotations) |
| 3 | RRnlp `punchline_bot` as a feature: key result sentence plus effect direction for each abstract | model (SciBERT, about 110M) | span candidate, agreement signal for the precision gate | 1–2 h, with a 45-minute install time box | `bwallace/RRnlp`, MIT, last push 2023-01 |
| 4 | Hedging and claim-strength cues: a hedged conclusion caps efficacy at ±1 and adds evidence_quality −1 | rule / lexicon | polarity intensity (QWK), evidence_quality | about 1 h | Yu et al. 2019 claim-strength scheme; BioScope hedge cues |

### 1. Change × good/bad rule (Niu et al.)

- **Method.** The papers ([PMC1560818](https://pmc.ncbi.nlm.nih.gov/articles/PMC1560818/),
  [PMC1839454](https://pmc.ncbi.nlm.nih.gov/articles/PMC1839454/)) tag the words after a *more* word (increased,
  prolonged, higher) or a *less* word (reduced, lower, decline). They then pair the tag with *good* or *bad* outcome
  words. Less-bad and more-good mean a positive outcome; more-bad and less-good mean negative; "no significant
  difference" means neutral. They used 306 cue words in four groups. Change-phrase features were the biggest single
  gain, and positive-outcome precision reached 0.87.
- **What we build.** A small lexicon of our own:
  - Oncology outcomes where higher is good: PFS, OS, ORR, DoR, response, intracranial response.
  - Outcomes where higher is bad: progression, death, recurrence, AEs, grade ≥3, ILD, discontinuation.
  - The change words.
  - A port of the HR/CI regex patterns from `mahmood726-cyber/dataextractor` (MIT, JS). Rule: HR < 1 with the upper
    CI below 1 means a significant benefit for the intervention.
- **Mapping to the guide.**
  - A significant favourable result about our product gives +2 ("significantly prolonged").
  - A favourable result without significance gives +1.
  - "Did not meet" or "no significant difference" gives −1 or 0. Tune which on dev.
  - Our product as the comparator flips the sign (guide: a rival beating osimertinib = −1).
- **Risk.** It is fitted to dev, like L2 and L3. Arm attribution in abstracts that compare A with B needs the
  product aliases. Check QWK before and after, as `DATA.md` §5 requires.
- **Test.** Log a new row: L3 plus this rule on PubMed only. Watch aspect F1 recall, QWK and span F1.

### 2. Evidence-Inference prompt for the 2B

- **Method.** This reuses the Evidence Inference task framing: given an (intervention, comparator, outcome) prompt,
  output "significantly increased", "significantly decreased" or "no significant difference", plus the evidence
  sentence. Wadhwa et al. 2023 ([PMLR v219](https://proceedings.mlr.press/v219/wadhwa23a.html)) had an LLM generate
  the intervention, comparator, outcome, evidence and label in one pass, and gained about 20 F1 points over pipeline
  methods.
- **For us.** The 2B returns `{outcome, our_arm: intervention|comparator|none, direction, sentence_no, hedged}` under
  a JSON grammar. Code then applies the pick-1 mapping, and the span builder quotes the sentence. This matches the
  pointer design (`PROBLEM.md` §4.1, item 4).
- **Findings that shape the prompt:**
  - Small models are bad at numbers. `hyesunyun/llm-meta-analysis` (Apache-2.0, [arXiv 2405.01686](https://arxiv.org/html/2405.01686v2))
    found open 7B models weak at numeric extraction, so regex handles HR/CI and the model never computes.
  - Fiorillo's swap test is a cheap sanity check for our pipeline. Exchange the intervention and comparator, and
    the direction should flip; Fiorillo flipped 67% of the time.
- **Data.** `bigbio/evidence_inference` on HF has MIT annotations, but the articles are under mixed PMC licenses.
  Fiorillo kept only the 1,431 CC BY / CC0 / public-domain training articles, so do the same. Uses: few-shot examples
  (abstract-only prompts) and, as a stretch, auxiliary LoRA data. **Rule R6 dedupe against test before any use.**
- **Test.** Log a new row once the 2B is up: the model fills PubMed aspects that L3 abstains on, scored on dev and on
  the silver hold-out.

### 3. RRnlp `punchline_bot`

- **What it does.** `pip install rrnlp`, then `TrialReader().read_trial({"ti":…, "ab":…})` returns
  `punchline_bot: {effect: "— no diff" | "↑ sig. increase" | "↓ sig. decrease", punchline_text}`, along with PICO
  spans, an RCT probability and a sample size. These are lightweight Trialstreamer models built on SciBERT.
- **Uses for us:**
  1. The punchline sentence is a strong candidate for the efficacy span. Gold spans sit across abstract sections,
     so measure the hit rate on dev before relying on it.
  2. A second opinion for the precision gate: emit an aspect only when the 2B and RRnlp agree on direction.
- **Risk.**
  - The README calls the models experimental.
  - It needs Python 3.9 (it fails on 3.10) and dependencies from the 2021 era.
  - Weights download on the first import, so they must be cached and shipped for the network-off run.
  - Last push was 2023.
  - Time-box the install on the Mac to 45 minutes. If it fails, drop it; picks 1 and 2 don't depend on it.

### 4. Hedging and claim strength

- **Source.** Yu et al. 2019 (EMNLP, "Detecting causal language use in science findings") labels PubMed conclusion
  sentences as no relationship, correlational, conditional causal or direct causal (repo
  `junwang4/correlation-to-causation-exaggeration`: about 3k annotated PubMed sentences plus 20k conclusion
  sentences). The repo has **no license**, so use it to inform a cue list only. Don't train on it or ship it.
- **Integration.** Two guards:
  1. Hedged conclusions ("may", "suggest", "potential", "associated with") cap efficacy at ±1. This applies the
     guide's "pick the milder" rule and protects QWK.
  2. Explicit caveats give evidence_quality −1, which L3 already partly does.
- The same scheme fits press releases. The companion COLING 2020 paper found causal overstatement in 22% of health
  press releases.

## Reference only (useful recipes, not usable as-is)

- **Fiorillo v0.5** (`johanneli/fiorillo-v0.5`, Apache-2.0, Qwen3-4B-Base). It reports a macro-F1 of 0.925 on the EI
  test set, calibrated (ECE 0.017), and runs on a laptop. It is **over the 3B cap**, needs a full article plus an
  (intervention, comparator, outcome) prompt, and returns no span. Its recipe is worth copying for a LoRA: LoRA r16 on
  every linear layer, a classification head, temperature calibration on validation data, and training only on
  articles with permissive licenses.
- **BioEvidence-LLM-1.5B** (MIT; Qwen2.5-1.5B QLoRA). It outputs YES/NO/MAYBE plus verbatim evidence quotes and an
  uncertainty field. It was **trained in about 2 hours on an RTX 3050 with 4 GB**, the same class as North's laptop
  GPU. That shows a LoRA can be trained on hardware we already have. Its output quality is unverified (43 downloads,
  no benchmark).
- **Small LLMs for biomedical claim verification** (BioNLP 2026). A Qwen2.5-3B QLoRA (r16, α32, lr 2e-4, 3 epochs)
  trained on about 1k examples was competitive. Code and adapters are released. It supports a LoRA on about 1k silver
  labels.
- **Sarker et al. 2011/2013**: document- and sentence-level outcome polarity with negation features (74.9% accuracy).
  Method only.

## Rejected

| Candidate | Reason |
|---|---|
| DeSpin (spin detection, MIT) | TensorFlow 1.13, a Tk GUI, models on an external file share, last updated 2020. Can't be integrated in time |
| Trialstreamer | No license; a server and database stack. RRnlp packages its models anyway |
| RobotReviewer | GPL-3.0 and heavy. It's a document-review system, not a library |
| Spark NLP clinical outcome polarity | Tavily listed it as Apache-2.0, but John Snow Labs' clinical models need a paid licence. Unverified and not offline-free |
| copenlu exaggeration detection | No license; macro-F1 about 0.6; needs abstract and press-release pairs |
| BioMistral-7B, clintrial-lm (7B), Llama-3-8B trial LoRA | Over the 3B cap. The Llama LoRA also predicts future trial outcomes, not what a text says |
| NLI4CT systems (SemEval 2023–24) | A different task: entailment against trial reports |
| SEETrials | GPT-3.5 by default; local use needs a 7B model |
| "Phi-3-clinical" and other models only the Tavily report names | Only the Tavily report supports them, and they are 3.8B, over the cap |

## Coverage and data quality

- **Strong:** B1 (Evidence Inference), B2 (RRnlp), B6 recipes.
- **Thin:**
  - B4 has no released lexicon of which direction is good for each outcome, so we build our own small one.
  - B5 spin tools are old and impractical.
  - B3 numeric extraction exists, but the models for it are 7B or larger.
- **Unverified follow-up:** the LREC 2018 "Medical Entity Corpus with PICO Elements and Sentiment Analysis" labels
  sentiment of intervention versus comparator. That matches our task, but I didn't confirm it is available.
- **The Tavily Research mini reports got several facts wrong**, which the GitHub and HF API checks caught:
  - Trialstreamer was listed as Apache-2.0; it has no license.
  - junwang4 was listed as MIT; it has no license.
  - Fiorillo was described as "2.5B encoder-only"; it is a 4B decoder.
  - A `run_inference.py` was said to return HRs.

  Treat those reports as leads, not facts. Every claim in this report was checked against the GitHub API, the HF API,
  or a README or paper fetched in this run.

## Spend

| Tool | Calls | Cost | Bucket |
|---|---|---|---|
| Tavily Research mini | 3 (plus 3 rejected submits that weren't charged) | 12–330 credits; exact figure not readable via OAuth | C |
| Tavily search (basic) | 5 | 5 credits | D |
| Tavily extract (basic) | 5 URLs | 1 credit | D |
| Exa MCP search | 5 (1 rate-limited) | about $0.03 (estimated) | ad-hoc |
| GitHub and HF APIs | 16 | free | — |

The Exa API key was never set, so Exa Agent and the `category: github` filter weren't used. The free MCP rate limit
was hit once. Before targets A, C and D, save the key to `~/.config/exa/key`.

## Suggested next step

Start with **pick 1 as rules on dev**. It needs no model, so it can run now while the Mac toolchain check (M1) is
pending. Log it as a new row. Then reuse the same mapping as the code half of **pick 2** once Qwen3.5-2B is serving.
Try pick 3 only if the Mac has a spare 45 minutes.
