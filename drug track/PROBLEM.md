# Signal-to-Dose: problem statement and build plan

> Spot the signals in a drug launch and track how the conversation moves, on a model you own.

HACK1984 Track 1 (Private Signals), sponsored by Within3. This file says what we are building, how it
is scored, where the points are, and the order we build in. The rules come from `README.md`,
`LABELING_GUIDE.md` and `RESEARCH_README.md`. If this file disagrees with them, they win.

---

## 1. The problem

When a drug launches, the launch team is buried in new trial data, safety reports, label changes,
competitor news, HTA decisions and commentary from doctors and patients. They need two answers every week:

1. **What happened that we should act on?** These are the signals.
2. **How is the conversation moving?** That is sentiment on efficacy, safety, convenience, access/cost and
   evidence quality, split by who is talking (researcher, HCP, patient, payer, regulator, company, media).

Our system reads public items about two EGFR-mutated NSCLC franchises:

| Code | Products |
|---|---|
| **A** | Tagrisso (osimertinib) |
| **B** | Rybrevant / Rybrevant Faspro (amivantamab) and Lazcluze (lazertinib) |

It produces two things:

- **Insight cards** with a headline, signal type, why it matters, citations (exact quotes plus URLs) and confidence.
- **A sentiment trend report**: scores from −2 to +2 by product × aspect × speaker, week over week, with
  the quotes behind every score.

**Hard constraint (track description):** inference runs on a **3B-parameter open model we host ourselves**. We use Qwen3.5-2B (§4.2). Nothing leaves
the machine. Judges run it **with the network off**, on the hidden test set and on **private transcripts**
we have not seen.

---

## 2. How we are judged

### 2.1 Leaderboard: `composite` on 240 hidden test items

`composite` is the plain mean of seven metrics (`scoring/score.py`):

| Metric | What it measures | Where the points are |
|---|---|---|
| `signal_macro_f1` | signal type, averaged over the classes present in gold | **Rare classes weigh as much as common ones.** One guideline item counts as much as 100 efficacy items. A wrong guess of a class that is absent from gold costs nothing extra. |
| `actionable_f1` | F1 on the "yes" class only | Only about 20% of dev items are "yes". Recall on the "yes" items matters. |
| `aspect_f1` | which of the 5 aspects are non-null | Precision matters. Don't fill aspects the text doesn't judge. |
| `polarity_qwk` | quadratic-weighted kappa on matched aspects | Sign errors are expensive; off-by-one is cheap. The guide says to pick the milder level when unsure. |
| `speaker_accuracy` | speaker on matched aspects | Close to fixed by source. Only news needs real judgement. |
| `span_f1` | bag-of-words token overlap with the gold span (lowercase, whitespace split) | Short spans are better. Keep the polarity-bearing words. |
| `citation_validity` | share of predicted spans that are an exact substring of the text | **A free 1.0.** Enforce it in code, never trust the model to do it. |

Missing items are scored as `none`, `no` and all aspects null.

### 2.2 Judge criteria beyond the leaderboard

- Do the citations support the claims? (Every card quote is a verbatim span with a highlighted source.)
- How do the trends look in the demo? (About 2,000 items over 22 months on a clean, readable chart.)
- **Network-off run on private transcripts.** This is a new document type: speaker turns, longer text, probably
  advisory-board or interview style.
- Usefulness: "Would a launch-intelligence expert act on it?"
- Privacy, plus **cost per 100 items**.
- Bonus: **effective use of Tavily and Exa**, and **a credible startup**.

---

## 3. The data (measured)

| File | Items | Notes |
|---|---:|---|
| `data/dev.full.jsonl` | 60 | gold labels (15 human-reviewed, 45 drafted by a frontier model and then reviewed) |
| `data/test_inputs.full.jsonl` | 240 | what we submit on. **Never hand-label these and never search for them.** |
| `data/unlabeled.full.jsonl` | 1,733 | free for self-training, distillation and the trend demo |

PubMed abstracts are already rehydrated, so no item has null text.

**Test set by source:**

| Source | Test | Unlabeled | How hard |
|---|---:|---:|---|
| pubmed | 104 | 896 | **Hard.** Signal type, aspects, polarity and span all need judgement. |
| ctgov | 40 | 142 | **Mostly rules.** Signal is trial_update and aspects are null unless a stop reason judges the drug. |
| fda_event | 37 | 553 | **Mostly rules.** Signal is safety, actionable is no, safety is −1 at most, speaker comes from the reporter type. |
| news | 30 | 96 | **Hard.** Snippet only, the speaker depends on who is quoted, and competitor framing matters. |
| press_release | 18 | 38 | Medium. Speaker is company. Watch for competitor moves and earnings releases. |
| fda_label | 10 | 8 | Medium. Separate meaningful label changes from cosmetic ones. |
| fda_notice | 1 | 0 | Rules: regulatory, yes, efficacy +1, regulator. |

About **78 of 240 test items (33%)** are ctgov, fda_event or fda_notice. The guide gives near-deterministic
rules for these, so rules should label them almost perfectly. The model's effort should go to pubmed, news,
press releases and labels.

**Dev label distribution:** signal efficacy 21, safety 16, trial_update 10, none 7, regulatory 2, and one each
of competitor_move, guideline, access_pricing and expert_opinion. Actionable: 12 yes, 48 no. Aspects:
efficacy 22, safety 22, evidence_quality 8, convenience 3, access_cost 1. Polarity: −1 ×25, +1 ×18, +2 ×9,
0 ×4 (no −2 in dev). Speaker: researcher 31, company 10, hcp 7, media 4, patient 3, regulator 1.

The rare classes (guideline, access_pricing, competitor_move, regulatory, expert_opinion) decide macro F1,
and dev has almost no examples of them. That gap is the main job for the Tavily and Exa augmentation.

---

## 4. Solution architecture

```
                    ┌──────────── BUILD TIME (network on) ────────────┐
 Tavily / Exa ────► knowledge pack (aliases, trials, rivals, bodies, timeline)
                    augmentation corpus for the rare classes (deduped against test)
 Frontier teacher ► silver labels on unlabeled + corpus ──► LoRA fine-tune of the ≤3B student
                    └─────────────────────────────────────────────────┘
                                         │ weights + knowledge/*.json
                    ┌──────────── RUN TIME (network off) ─────────────┐
 item ─► normalize ─► source router ─┬─► rules (ctgov, fda_event, fda_notice, fda_label skeleton)
                                     └─► ≤3B model, JSON-schema constrained ─► span snapper ─► rule guards
                                                         │
                                       labels.jsonl (submission format)
                                                         │
                         aggregator ─► insight cards + weekly sentiment trends ─► UI
                    └─────────────────────────────────────────────────┘
```

### 4.1 Components

1. **Normalizer.** Splits text into sentences and keeps character offsets. It also detects transcripts
   (speaker turns such as `Dr. X:`, `Patient:` or `Q:`/`A:`) and splits them into turns, each with a speaker tag.
2. **Source router and rule engine** (`rules.py`). Turns the guide's per-source rules into code:
   - `ctgov` → `trial_update`. Aspects are null unless the stop reason matches futility/efficacy (efficacy −2)
     or toxicity (safety −2). Actionable is yes for terminations of our trials and new phase 3 registrations.
   - `fda_event` → `safety`, actionable no. Speaker comes from the `Reporter` field. Safety −1 with the reaction
     words as the span. Special reactions follow the guide: drug ineffective or progression gives efficacy −1,
     can't afford gives access_cost −1, and off-label use, product use issue or no adverse event gives null.
   - `fda_notice` → regulatory, yes, efficacy +1, regulator.
   - The rules cover the skeleton of each prediction. The model only fills what the rules leave open.
3. **Student model (Qwen3.5-2B, set by profile).** It is fine-tuned on teacher labels and called with **JSON-schema constrained decoding**
   (llama.cpp grammar, or vLLM/Outlines guided JSON) so every output parses. The prompt holds the condensed
   labeling guide, the knowledge-pack facts relevant to the item, and 2 or 3 retrieved dev examples from the
   same source.
4. **Span snapper.** This guarantees `citation_validity = 1.0`.
   - If the predicted span is an exact substring, keep it, then trim it to the shortest sub-phrase that still
     holds the polarity cue (span F1 rewards short spans).
   - If not, fuzzy-align it (rapidfuzz partial ratio over sentence windows) to the best exact substring within
     **one sentence** (ruling 10). Never cross a "…".
   - If nothing aligns above a threshold, drop the aspect rather than cite text that isn't there.
5. **Guards.** These apply rules from the guide that small models tend to break: polarity is clipped to ±1
   unless a strong cue word is present ("statistically significant", "failed", "boxed warning"); the
   fda_event cap; "no new safety signals" is 0 and "manageable" is +1; earnings releases are competitor_move
   with no aspects; preclinical work is efficacy with actionable no.
6. **Aggregator.** Builds weekly buckets on `published` and computes mean polarity with n per
   (product, aspect, speaker). It flags shifts (|Δ| ≥ 0.5 with n ≥ 3, or a sign flip) and keeps the
   top quotes behind each cell.
7. **Card writer.** Groups actionable items into events using the knowledge-pack trial names and dates
   (MARIPOSA OS, FLAURA2 OS, a NICE decision). The student model writes the headline and "why it matters" from
   the cited spans only. Confidence is the calibrated agreement between sampled outputs, checked on dev.

### 4.2 Model choice and hardware

**Dev hardware:** a friend's MacBook Pro (Apple Silicon). It runs Qwen3.5-9B and Gemma 4 12B. Judges run
the final model on their own hardware.

**Decision: we follow the 3B cap.** `README.md` sets no size limit, but the track description says "It runs on
a 3B-parameter open model that you host", so we treat that as binding. We read it strictly as **total
parameters ≤ 3B**. **We iterate on Qwen3.5-2B.** We also stay ready to switch to a bigger model if the rule
changes.

Sizes below are from the Hugging Face and Google model cards, checked with Exa on 2026-11-07:

| Model | Parameters | Within the cap? | Role |
|---|---|---|---|
| **Qwen3.5-2B** | 2.27B | Yes | **Primary student. Every iteration runs on this.** |
| Qwen2.5-3B-Instruct / Llama-3.2-3B-Instruct | about 3B | Yes | Fallback if tooling for Qwen3.5 breaks |
| Gemma 4 E2B | 2.3B effective, 5.1B total | No (strict reading) | Skip unless the rule changes |
| Qwen3.5-4B / Gemma 4 E4B | 4.66B / 4.5B effective | No | Skip unless the rule changes |
| **Qwen3.5-9B** | 9.65B | No | **Standby profile.** Scored at checkpoints so we know the gap, and the swap target if the rule changes. Also the higher-accuracy option in the pitch (§7) |
| Gemma 4 12B | 11.95B | No | Second standby if the 9B underperforms |

**Prepared for both.** The pipeline stays model-agnostic, so switching model is a config change, not a rebuild:

- **Model profiles** live in `config/models.yaml`. Each profile holds the base model, adapter path, GGUF
  path, context length, chat template and decoding settings. `MODEL_PROFILE=qwen35-2b` is the default and
  `MODEL_PROFILE=qwen35-9b` is the standby.
- The prompts, JSON schema, rules, span snapper, guards and aggregator are shared by all profiles. None of them
  carry model-specific logic. If a prompt tweak helps the 2B and hurts the 9B, keep it in the profile, not in shared code.
- `train/` takes the base model as an argument. The same silver dataset trains both, so the 9B adapter only costs
  extra training time.
- `EVAL.md` has a column per profile. The 2B is scored on every change. The 9B is scored at milestones (M0
  zero-shot, M3 fine-tuned) so the gap is always known.
- The UI's "Under the hood" screen shows the active profile, its size, latency and cost per 100 items. If the rule
  changes, the demo can show a side-by-side of 2B and 9B.

**Tooling on the Mac:**
- Fine-tuning: LoRA with `mlx-lm` on Apple Silicon. A 2B model fits easily.
- Serving: llama.cpp (Metal) with a GGUF and a JSON-schema grammar, or `mlx-lm` plus Outlines. Ship a GGUF that
  also runs on CPU, because we don't know the judges' hardware. Measure tokens per second and show the cost per
  100 items in the UI.
- **Check this first (the first hour of M0):** Qwen3.5 uses a new hybrid Gated DeltaNet layout. Confirm that the
  installed `mlx-lm` and llama.cpp versions can load, LoRA-train, convert to GGUF and grammar-decode Qwen3.5-2B.
  If any step fails, fall back to Qwen2.5-3B. The 9B is the same architecture, so the check covers it too.
- Turn off Qwen3.5's thinking mode for labeling. We want JSON only, faster, and cheaper per 100 items.
- Fine-tuning recipe: 2 or 3 epochs on about 2,000 or more silver examples, plus the 60 gold examples weighted
  higher.
- A 2B model needs more help than a 9B. Lean on the rule engine, the knowledge-pack cues and the guards, and split
  the work into small calls (classify, then aspects) if one combined call is unreliable.

### 4.3 Teacher labeling (distillation)

- The teacher is a frontier model prompted with the full `LABELING_GUIDE.md` (rulings included) and few-shot
  dev examples. **Calibrate it on dev first** and report its composite on the 15 human-reviewed items.
  The gold was drafted by a frontier model under the same guide, so a well-prompted teacher should track it closely.
- It labels `unlabeled.jsonl` and the augmentation corpus. **It never labels `test_inputs`.**
- **Confirmed allowed:** sending unlabeled items to a hosted frontier API for labeling.
- Put the guide and few-shot examples in a shared prompt prefix so prompt caching applies. Run 50 items
  first, log the spend, then run the rest.
- The local 9B and 12B models are not needed as teacher. The 9B is the standby profile in §4.2.

### 4.4 Inference passes (quality versus cost)

| Mode | Calls per item | Use |
|---|---|---|
| fast | 1 (all fields in one JSON) | live demo, cost figure |
| accurate | 1 classify + 1 aspects, self-consistency ×3 on polarity | leaderboard submission |

Report both. The cost per 100 items is a judged number.

---

## 5. Strategy for maximising score, in priority order

1. **Rules first.** Get ctgov, fda_event and fda_notice right with no model. That covers 33% of the test set.
2. **Citation validity of 1.0** from the snapper. It is free and one-seventh of the composite.
3. **Rare-class recall** for macro F1: knowledge-pack cues (HTA and payer bodies → access_pricing; NCCN/ESMO/ASCO
   → guideline; rival drug beating osimertinib → competitor_move; FDA/EMA action → regulatory) plus augmentation data.
4. **Actionable recall:** new pivotal data, label changes, approvals, guideline changes, HTA decisions,
   competitor moves, terminations and new phase 3 registrations default to yes.
5. **Aspect precision:** train with null-heavy examples and add a "does the text judge the product?" gate.
6. **Polarity:** default to the milder level and only allow ±2 with strong cue words. Optimise QWK on dev.
7. **Short spans:** train on gold-style short spans. The snapper trims anything over 15 words.
8. **Evaluate every change** with `python scoring/score.py --gold data/dev.jsonl --pred out/dev_pred.jsonl --items data/dev.full.jsonl`
   and add a row to the experiment log, `../docs/experiments/log.md` (the single results table; it replaces the planned `EVAL.md`). With only 60 dev items, beware overfitting, and also score on a
   held-out slice of teacher-labeled data.

---

## 6. Tavily and Exa: effective use (bonus points)

There are two layers, and **neither is called at scoring time**. The offline core never imports either SDK
(`grep -rE 'tavily|exa' src/inference` must come back empty). Budgets, hard rules R1 to R9 and the ledger
follow `RESEARCH_README.md`. Never put test-item text in a query.

### 6.1 Build-time: makes the offline model smarter

| Job | Tool | Output |
|---|---|---|
| Trial → NCT → product → phase table for A, B and rivals | **Exa Agent** (`effort: medium`, `outputSchema`) | `research/knowledge/trials.json`, `rivals.json` |
| Regulator, HTA, payer and guideline body list with speaker roles | **Tavily search** (basic) + extract on primary sources | `bodies.json` |
| Dated event timeline 2025-01 to 2026-10 (approvals, NICE, NCCN, label changes) | **Tavily search** `--topic news` with date bounds | `timeline.json`, which grounds event clustering for the cards |
| Rare-class corpus (HTA appraisals, guideline updates, payer coverage, competitor releases) | **Tavily map → extract**, plus **Exa "find similar"** from 2 or 3 seeds per class | `research/corpus/<class>/`, deduped against test (R6), labeled by the teacher |
| Method research (span extraction, ordinal ABSA, distillation, choosing a 3B model) | **Exa** research-paper and GitHub categories, and **Tavily Research** `mini` | `research/reports/`, which feeds the decisions in §4 |

Each knowledge-pack entry keeps its source URL, so the UI can show where the system's background knowledge came from.

### 6.2 Product-time: live mode (network on, opt-in)

This is what makes it a product rather than a batch job. All of it is shown in the demo, and all of it can be switched off.

- **Watchtower (Tavily).** Scheduled news and regulatory searches (`max_age_hours` = interval, as in the
  `tavily-monitor` pattern) for each product, trial and HTA body. New hits become items, go through the
  **same local model**, and show up as fresh cards.
- **Expand this signal (Exa).** On any card, a semantic "find similar" search pulls related coverage and papers
  so the team can see how far an event has spread. The results are labeled locally.
- **Landscape brief (Tavily Research mini).** A weekly competitive context paragraph, kept separate from the
  model's cited claims.
- **Provenance and spend panel.** Shows the ledger from `research/ledger.jsonl`: credits used by bucket, and
  which knowledge entries came from which call.

Only public, generic queries leave the machine (product names, trial names, body names), never customer data
or item text. The demo shows the **air-gap toggle**: live mode greys out, and the core keeps working.

---

## 7. The startup

**Working name:** Signal-to-Dose. (Run one Tavily search for name conflicts before using it on slides.)

**One line:** On-prem launch intelligence for pharma brand teams. It turns the noise around a drug launch
into cited, actionable signals and sentiment trends, and no data leaves your walls.

**Who buys:** brand and launch teams, medical affairs, market access and competitive intelligence at
mid-size and large pharma, starting with oncology launches. Oncology has many data readouts, fast competition
and heavy HTA exposure.

**Why now, and why us:**
- Launch teams already pay for social listening and CI, but generic tools don't know what "MARIPOSA OS" or
  "NICE rejected on cost" means for a brand plan.
- **Compliance blocks cloud LLMs.** Field notes, advisory-board transcripts and MSL insights are confidential,
  and MLR and privacy teams won't send them to a third-party API. A 3B model on the customer's own box
  removes that objection.
- **Pharmacovigilance hook.** Any adverse-event mention in listening data may trigger reporting duties. Our
  safety-signal flag with an exact quote is an AE-triage feature that compliance teams want.
- **Trust from citations.** Every score traces back to a verbatim quote. No quote, no claim.

**Product tiers:**
1. *Public Pulse.* Public sources (the hackathon scope), with live monitoring through Tavily and Exa.
2. *Private Signals.* The customer's own advisory-board transcripts, MSL field notes and call notes,
   processed fully offline. This is the private-transcript judging criterion turned into a product.
3. *Launch Room.* Weekly brief, alerts and export to slides.

**Runs on a laptop.** The demo runs entirely on a MacBook Pro with the network off, which makes the on-prem
claim visible on stage.

**Business model:** annual licence per brand, deployed on-prem or in the customer's VPC, with pricing anchored
to what a CI agency retainer costs. **Unit economics:** our measured cost per 100 items on a single commodity
GPU or CPU box, shown live in the UI, against a frontier-API equivalent.

**Model sizes as a product lever:** the 2B runs on any laptop at the lowest cost per 100 items. Customers with a GPU server can choose the 9B for higher accuracy on the same pipeline.

**Moat:** a labeled launch-signal ontology, per-therapeutic-area fine-tunes, and the provenance and compliance
layer.

**Before the pitch:** get market size, CI spend and competitor facts from one `tavily-research` mini run,
cited on the slide. Don't put unsourced numbers on a slide.

---

## 8. The demo UI

Stack: FastAPI backend serving precomputed JSON plus a live `/analyze` endpoint, and a React/Vite or
single-page frontend. Everything is served from localhost, so it works with the network off.

**Screens:**

1. **Signal feed (home).** Insight cards sorted by actionability, then recency. Each card has the signal-type
   chip, product badge (A, B or both), headline, why it matters, confidence bar, and citation chips. Clicking
   a chip opens the source with the quote highlighted and a "verbatim ✓" badge. Filters: product, signal
   type, actionable only, date range.
2. **Sentiment trends.** One line per aspect over weeks on a −2 to +2 axis, with a product toggle and a
   speaker filter. Shift markers show where a delta fired. Clicking a week point shows the quotes behind the score.
3. **Heatmap.** Aspect × speaker for a chosen period, diverging colour, n shown in each cell. This answers
   "how do payers feel about access, compared with HCPs?" at a glance.
4. **This week.** An auto brief listing the top 3 signals, the biggest sentiment moves and new risks, each cited.
5. **Analyze.** Paste or upload any text, including a **transcript**, and get labels, aspects with highlighted
   spans, and a card, live on the local model. A latency and cost-per-100 readout and a **network: OFF**
   indicator stay visible.
6. **Under the hood.** Dev scorecard (all 7 metrics plus composite, before and after fine-tuning), the model
   card, the Tavily/Exa provenance and spend panel, and the live-mode toggle.

**Demo script (about 4 minutes):**
1. Hook (20s): "MARIPOSA OS lands. Is it a threat to Tagrisso, and how are doctors reacting?"
2. Feed (60s): open the top competitor_move card and click through to the verbatim quote.
3. Trends (60s): Rybrevant convenience moves up after the subcutaneous Faspro news; Tagrisso efficacy dips
   on competitor framing. Drill into the quotes behind it.
4. Air-gap (45s): switch the network off and paste a mock advisory-board transcript. Cards and sentiment come
   back from the local 3B model, with the cost per 100 items on screen.
5. Live mode (30s): network back on. Watchtower pulls a fresh item through Tavily, and Exa expands it.
6. Close (25s): the startup slide covering who pays, why on-prem, and the PV hook.

(Pick the hero storyline only after the trend data is computed. Show what the data actually says.)

---

## 9. Repo layout (target)

```
drug track/
  PROBLEM.md            ← this file
  (results: ../docs/experiments/log.md; lessons: ../docs/solutions/; repo root is hack1984/)
  src/
    inference/          ← offline core: normalize, rules, model client, snapper, guards (no network imports)
    rules/predict.py    ← current rules-only predictor (levels 1-3)
    eval/               ← score_dev.sh, log_exp.py
  config/models.yaml    ← model profiles: qwen35-2b (default), qwen35-9b (standby)
    aggregate/          ← trends + cards
    train/              ← teacher labeling, dataset build, LoRA
    live/               ← Tavily/Exa connectors (online only)
  research/             ← per RESEARCH_README §7 (knowledge/ ships with the model)
  models/<profile>/     ← GGUF + LoRA adapter for each profile
  app/                  ← FastAPI + frontend
  out/
    dev_pred.jsonl
    submission.jsonl    ← 240 lines, one per test item
  run_offline.sh        ← one command: items in, submission + trends + cards out, network off
```

---

## 10. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Baseline | Mac toolchain check (§4.2) passes. `config/models.yaml` has `qwen35-2b` and `qwen35-9b` profiles. Rules plus zero-shot Qwen3.5-2B plus the snapper produce `dev_pred.jsonl` with a composite in `EVAL.md`. Score zero-shot 9B once for the gap |
| M1 | Knowledge pack | `research/knowledge/*.json` built with Tavily and Exa, checked against primary sources, loaded offline |
| M2 | Silver data | Teacher calibrated on dev, then labels the 1,733 unlabeled items and the rare-class corpus |
| M3 | Fine-tuned student | LoRA Qwen3.5-2B beats its zero-shot dev composite. Pick fast or accurate mode. Train the 9B adapter on the same data and record its score (standby) |
| M4 | Trends + cards | All about 2,033 items labeled, weekly aggregates and cards as JSON |
| M5 | UI | All six screens working on localhost |
| M6 | Offline proof | `run_offline.sh` passes under `unshare -rn` (or `docker --network none`), including a mock transcript |
| M7 | Submission + pitch | `out/submission.jsonl` validated by the scorer's loader, plus the demo script and startup slides |

If time runs short, cut in this order: live mode (M5 screen 6 extras), then the accurate mode's
self-consistency, then the heatmap. Never cut M0, M6 or citation snapping.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Private transcripts look nothing like the training items | Transcript detection and turn splitting, a speaker-from-turn mapping (Dr./MD → hcp, patient → patient, payer/PBM → payer), and synthetic transcripts in training built from teacher labels |
| A 3B model breaks JSON or invents spans | Constrained decoding, the snapper, and guards |
| Overfitting to 60 dev items | Also score on a held-out teacher-labeled slice and keep rules close to the guide's wording |
| Test leakage through research | R1 and R6 from RESEARCH_README, the dedupe log, and no test text in any query |
| Rare classes are still missed | Augmentation corpus, knowledge-pack cue features, and rule fallbacks for HTA, guideline and earnings |
| Hidden network calls in the core | CI grep check plus the network-off run in M6 |
| Hardware differs on judge day | Ship a GGUF that runs on CPU, and pin versions in `requirements.txt` |
| Qwen3.5 architecture unsupported in MLX or llama.cpp | Toolchain check in M0, with Qwen2.5-3B as the fallback |
| The 3B rule is relaxed or dropped | Switch `MODEL_PROFILE` to `qwen35-9b`. Its adapter is already trained and scored, so this is a config change |
| A 2B model is too weak on pubmed and news | More rules and guards, split calls, self-consistency voting. The 9B gap in `EVAL.md` shows how much is left to win |

---

## 12. Definition of done

- [ ] `out/submission.jsonl` has 240 lines, all fields valid, every span an exact substring
- [ ] Dev composite and per-metric scores recorded in `EVAL.md`
- [ ] `run_offline.sh` runs end to end with the network off, on test items and on a sample transcript
- [ ] UI demo runs from localhost, with trends drawn from about 2,000 items
- [ ] Tavily/Exa ledger, knowledge-pack provenance and leftover budget documented
- [ ] Cost per 100 items measured and shown
- [ ] Model weights or name plus adapter, code and README ready to hand in
- [ ] Pitch: problem, product, why on-prem, PV hook, business model and demo
