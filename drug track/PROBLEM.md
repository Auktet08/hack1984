# Signal-to-Dose: problem statement and build plan

> Spot the signals in a drug launch and track how the conversation moves, on a model you own.

HACK1984 Track 1 (Private Signals), sponsored by Within3. This file covers what we are building, how it is
scored, the decisions made so far, and a **draft** plan for the remaining time. The rules come from
`README.md`, `LABELING_GUIDE.md` and `RESEARCH_README.md`. If this file disagrees with them, they win.

**Related files:** `DATA.md` (measured data and scorer facts, read it for any number not repeated here) ·
`../docs/experiments/log.md` (**the only results table**) · `../docs/solutions/` (lessons learned) ·
`../docs/ideation/2026-11-07-hack1984-private-signals-ideation.html` (ranked ideas and rejections) ·
`../docs/ideation/2026-11-07-lean-plan.md` (**what we build now**) · `research/reports/{A,B,C,D}-*.md` (open-source
research) · `../CLAUDE.md` (experiment protocol) · `../CONCEPTS.md` (vocabulary).

---

## 0. Read first: status as of Sat 2026-11-07, 14:30 EST

**Plan status: DRAFT, not committed.** We discuss §10 (schedule) and §13 (open questions) before building more.
**Since 13:00:** North chose the **lean plan** (decision 8). §4.3, §5, §10 and §13 were redrafted to match, and
the open-source research for targets A–D is done (`research/reports/`).

**Competition theme: privacy-first startups.** The pitch and demo should show a product that is private by design
(a local model, network off, nothing leaves the customer's hardware), not a product with privacy added later. This
frames the pitch only. It doesn't add privacy engineering work beyond running the model locally.

**Deadline: Sun 2026-11-08, 11:00 EST, for everything:** submission file, code, weights, demo and pitch.
That leaves about 22 hours including sleep.

**Team:** three people. North owns the **pipeline**. The other two roles are proposed in §10 and not yet agreed.
**Hardware:** a friend's MacBook Pro (Apple Silicon), available all day, is the only machine for model work.
North's laptop has an RTX 3050 Ti with 4 GB.

**Where we are:**
- The rules-only predictor `src/rules/predict.py --level 3` scores **0.843 dev composite** (0.864 on the
  15 human-reviewed items). See log row E009. Levels 2 and 3 were fitted to dev, so expect test to come in lower.
- Its per-metric dev scores:

  | signal mF1 | actionable F1 | aspect F1 | QWK | speaker | span F1 | citation |
  |---|---|---|---|---|---|---|
  | 0.856 | 0.762 | 0.617 | 0.933 | 1.0 | 0.731 | 1.0 |

- **The headroom is aspect recall.** Only 25 of 56 gold aspects are matched. Most of the misses are PubMed
  efficacy claims with no cue word. After that come span F1 and actionable F1.
- No model has run yet, the Mac toolchain is untested, and no teacher labels exist yet.

**Decisions in force:**
1. **3B cap is binding.** The track description says a 3B-parameter model, so we read that as total
   parameters ≤ 3B. `README.md` itself sets no limit. **We iterate on Qwen3.5-2B.** Qwen3.5-9B stays on standby
   in case the rule changes (§4.2).
2. **Teacher labels are allowed** on the 1,733 unlabeled items from a hosted frontier model. Never send test items.
3. **Rules come first.** Rules keep the final say where they fire. The model fills the gaps.
4. **ctgov actionable stays "no"**, even for phase 3 registrations: dev shows 10 of 10 "no", although the guide
   says "usually yes".
5. **Self-consistency voting is rejected.** The ideation found it costs more and doesn't address the main risk.
6. **Tavily and Exa are used at build time and in opt-in live mode only**, never in the scored run.
   Every call is logged in `research/ledger.jsonl`.
7. **Always keep a valid submission on disk.** It starts as the rules-only output and is replaced only by something that scores better.
8. **Lean plan: stop chasing composite on dev** (North, Sat 14:30). Even perfect aspects reach only 0.904 (E017),
   and each remaining lever is worth +0.005 to +0.025, below dev noise. The time goes to what judges see beyond the
   leaderboard instead: the network-off transcript run, citations, the demo, usefulness, cost per 100 items and the
   startup. One model path, built for transcripts first. **Cut:** LoRA, the score-tuning experiments, and (proposed,
   to confirm) teacher labels. Details: `../docs/ideation/2026-11-07-lean-plan.md`.
9. **Gemini Flash stands in for the local model on the startup side** (North, Sat evening) until the trained 2B
   lands. `src/startup/label.py --backend gemini` writes `out/startup/labels/<corpus>.jsonl`. Every row carries
   `meta.stand_in: true`, and the UI must show it. The local backend writes the same file, so the switch is one flag.
   Only public material goes to Gemini. The scored submission and the network-off air-gap demo still need the
   local model.

---

## 1. The problem

When a drug launches, the launch team is buried in new trial data, safety reports, label changes, competitor
news, HTA decisions and commentary from doctors and patients. Each week they need two answers:

1. **What happened that we should act on?** These are the signals.
2. **How is the conversation moving?** That means sentiment on efficacy, safety, convenience, access/cost and
   evidence quality, split by who is talking (researcher, HCP, patient, payer, regulator, company, media).

The products are **A** = Tagrisso (osimertinib) and **B** = Rybrevant / Rybrevant Faspro (amivantamab) +
Lazcluze (lazertinib), in EGFR-mutated NSCLC.

**Deliverables:**
- **Per-item labels** in the submission format: signal type, actionable, and five aspects, each with
  polarity, speaker and a verbatim span.
- **Insight cards**: headline, signal type, why it matters, citations (verbatim quotes plus URLs) and confidence.
- **Sentiment trend report**: −2 to +2 by product × aspect × speaker, week over week, with the quotes behind each score.

**Constraint:** a self-hosted model of 3B parameters or fewer. Judges run it
**with the network off**, on the hidden test set and on **private transcripts** we haven't seen.

---

## 2. How we are judged

**Leaderboard:** `composite` on 240 hidden test items. It is the plain mean of seven metrics: signal macro-F1,
actionable F1, aspect F1, polarity QWK, speaker accuracy, span token-F1 and citation validity. The scorer has
traps; read `DATA.md` §5 and `../docs/solutions/best-practices/composite-scorer-*.md` before tuning. In short:
- Polarity, speaker and span are scored **only on matched aspects**, so a wrong extra aspect costs more than a missed one. Favour precision.
- **QWK cliff:** if every matched polarity is the same value, one deviant gold label drops QWK from 1.0 to 0.
  Keep the matched polarities varied.
- **Never submit zero aspects**, which scores 0.167.
- Macro-F1 averages only the classes present in gold, so each rare class is worth about 1.6 composite points.
- Citation validity is an exact-substring check. Enforce it in code.

**Judges also weigh:** whether the citations support the claims; how the trends look in the demo; a
**network-off run on private transcripts**; usefulness ("Would a launch-intelligence expert act on it?");
cost per 100 items. **Bonus points:** effective use of Tavily and Exa, and a credible startup.

**Theme: privacy-first startups.** The startup is judged as a privacy-first business, so lead with what stays on the
customer's hardware and why that matters to the buyer. See `STARTUP.md` §10 for how we position against the sponsor,
Within3.

---

## 3. The data (summary; details in `DATA.md`)

| File | Items | Use |
|---|---:|---|
| `data/dev.full.jsonl` | 60 | gold (15 human-reviewed, 45 drafted by a frontier model, then reviewed): tune, eval, few-shot |
| `data/test_inputs.full.jsonl` | 240 | submission only. **Never design rules from it, never label it, never search for it** |
| `data/unlabeled.full.jsonl` | 1,733 | trend demo (labeled by our pipeline overnight); teacher labels only if §4.3 is kept |

Test by source: pubmed 104 · ctgov 40 · fda_event 37 · news 30 · press_release 18 · fda_label 10 · fda_notice 1.
Rules handle ctgov, fda_event and fda_notice (78 items) almost deterministically. The model's work is PubMed,
news, press releases and fda_label judgement calls (162 items), **plus transcripts, where no source rules apply.**

Dev is not shaped like test: it has fewer news items and no fda_notice. Unlabeled is 73% product A. Dev has only
one example each of competitor_move, guideline, access_pricing and expert_opinion.

---

## 4. Solution architecture

```
                 ┌───────────── BUILD TIME (network on) ─────────────┐
 Tavily / Exa ─► knowledge pack (aliases, trials, rivals, bodies, timeline)
 (cut in the lean plan: frontier teacher ─► silver labels ─► hold-out + LoRA; see §4.3)
                 └───────────────────────────────────────────────────┘
                                     │ knowledge/*.json + weights
                 ┌───────────── RUN TIME (network off) ──────────────┐
 item / transcript ─► normalize (sentences, turns, offsets) ─► source router
     ├─► rules (ctgov, fda_event, fda_notice, fda_label skeleton, earnings, rare-class cues)
     └─► Qwen3.5-2B, JSON-schema constrained ─► span builder ─► guards ─► merge (rules win)
                                     │
            labels.jsonl ─► aggregator ─► cards.json + trends.json ─► UI
                 └───────────────────────────────────────────────────┘
```

### 4.1 Components

1. **Normalizer.** Splits text into numbered sentences, then numbered **clauses**, and keeps character offsets.
   Clauses split on `, ; : — (` and before "that", wh-words and subordinating conjunctions, and on "and/or" only
   when both sides have about 3 or more words. It never lets a sentence cross `…` or `[...]`, and strips
   press-release navigation boilerplate while keeping the original offsets. It detects transcripts (`Dr. X:`,
   `Patient:`, `Q:`/`A:` turns) and tags each turn with a speaker role. The role rules, in order:
   `Name (Title, Org):` → self-identification ("as a medical oncologist") → roster → `unknown`.
2. **Rule engine.** Starts from the existing `src/rules/predict.py` (levels 1–3) and moves into `src/inference/`.
   Covers the per-source rules from the guide, rulings 1–10, rare-class title cues and cue-word aspects. It gets a
   "confident or abstain" output so the model knows what is left open.
3. **Student model (Qwen3.5-2B, chosen by profile).** Runs only on what the rules leave open: PubMed, news and
   press-release aspects without cue words, signal-type fallback, fda_label judgement, and all transcript turns.
   **Transcripts come first** (decision 8). Output is constrained to a JSON schema with the evidence field first
   (`unit_id` before aspect and polarity). The schema text is also written into the prompt: with a grammar alone,
   a 2B loses accuracy (research report C). The prompt holds the relevant guide section, knowledge-pack facts for
   the item, and 2 or 3 dev examples from the same source.
4. **Span builder.** Guarantees citation validity of 1.0. The model returns `{unit_id, aspect, polarity}`, where
   `unit_id` is an enum of the item's clause IDs, never free text. Code quotes that clause and trims it to about
   8 words with no trailing punctuation. Clauses, not sentences: on dev the best clause scores 0.673 span F1
   against 0.395 for the whole sentence (ideation I2/I3). There is no free text, so nothing needs snapping.
5. **Guards.** Polarity is clipped to ±1 unless a strong cue word is present. The fda_event cap of −1 applies.
   "No new safety signals" is 0 and "manageable" is +1. Earnings releases are competitor_move with no aspects.
   Preclinical studies are efficacy with actionable no. Speaker comes from the source table. A pre-submit check
   makes sure matched polarities aren't all one value. **AE triage flag** (for the demo and the pitch): when safety
   is non-neutral, check the four ICH E2D(R1) minimum criteria (AE quote, product, patient cue, reporter role) and
   show a "triage candidate" badge. Never word it as a reporting decision.
6. **Aggregator.** Builds weekly buckets on `published` and computes the mean polarity and n per
   (product, aspect, speaker). It flags shifts (|Δ| ≥ 0.5 with n ≥ 3, or a sign flip) and keeps the top quotes per cell.
7. **Card writer.** Groups actionable items into events using knowledge-pack trial names and dates. v1 headlines
   are templated from title, signal and span. Headlines written by the model are a stretch goal. Confidence comes
   from the source prior plus whether rules and the model agree.

### 4.2 Model choice and hardware

**Decision: follow the 3B cap (total parameters) and iterate on Qwen3.5-2B.** Sizes are from the model
cards, checked with Exa on 2026-11-07 and logged in the ledger:

| Model | Parameters | Within cap? | Role |
|---|---|---|---|
| **Qwen3.5-2B** | 2.27B | Yes | **Primary. Every iteration runs on this** |
| Qwen2.5-3B-Instruct / Llama-3.2-3B-Instruct | about 3B | Yes | Fallback if the Qwen3.5 toolchain breaks |
| Gemma 4 E2B | 2.3B effective, 5.1B total | No (strict reading) | Skip unless the rule changes |
| Qwen3.5-4B / Gemma 4 E4B | about 4.5B | No | Skip unless the rule changes |
| **Qwen3.5-9B** | 9.65B | No | **Standby.** Score it zero-shot once for the gap. Swap target if the rule changes. Higher-accuracy tier in the pitch |
| Gemma 4 12B | 11.95B | No | Second standby |

**Ready for both sizes:** model profiles live in `config/models.yaml` (`qwen35-2b` is the default and
`qwen35-9b` the standby), selected by `MODEL_PROFILE`. Prompts, schema, rules, span builder, guards and
aggregator are shared, so switching is a config change. Within this hackathon the 9B stays un-tuned
unless there is spare Mac time.

**Mac toolchain:**
- **First check** (Qwen3.5's Gated DeltaNet layout is new): can `mlx-lm` and llama.cpp load the 2B, decode
  with a JSON-schema grammar, and convert to GGUF? Also measure tokens per second. (The LoRA smoke test is
  dropped with the LoRA.)
  If any step fails, fall back to Qwen2.5-3B.
- Serving: llama.cpp (Metal) with a GGUF and a grammar, or `mlx-lm` plus Outlines. The delivered runtime should be
  a GGUF that also runs on CPU, because we don't know the judges' hardware.
- Turn Qwen3.5's thinking mode off.
- Measured throughput decides two things: how long labeling the full 2,033 items takes, and the cost per 100 items.

### 4.3 Teacher labeling

**Proposed cut (decision 8, to confirm with the team).** Its three uses (honest scoreboard, few-shot pool, LoRA
data) all serve score-chasing. Few-shot examples come from dev instead, and trends and cards come from our local
pipeline anyway. If it is kept, the original plan below still applies.

- A frontier model prompted with the full `LABELING_GUIDE.md` (rulings included) plus dev few-shot examples, with a
  shared prompt prefix so prompt caching applies.
- **Calibrate on dev first** and log the teacher's dev composite as a row. Then run 50 unlabeled items, check the
  spend, and run the rest. It never touches test.
- **Uses, in priority order:**
  1. **Honest eval set.** A held-out slice of silver labels: dev is tiny and the rules were fitted to it.
  2. **Few-shot pool** for retrieval by source.
  3. **LoRA training data** (stretch). Rebalance it: downsample fda_event and upweight news, press releases,
     fda_label and product B.
- The trends and cards in the demo come from **our local pipeline's** labels, not the teacher's. That is the
  claim we make.

### 4.4 Inference modes

| Mode | Calls per item | Use |
|---|---|---|
| fast | 1 (signal + aspects in one JSON) | live demo, transcripts, cost figure |
| split | 1 classify + 1 aspects | the submission, if dev shows it beats fast |

Report the cost per 100 items for each mode.

---

## 5. Score strategy: protect the score, don't chase it (decision 8)

The headroom is small: perfect aspects reach only 0.904 (E017), and every research-backed lever is worth +0.005 to
+0.025, below the ±0.055 dev noise. So:

1. **Protect.** Ship the rules-only safety net first (M0). Keep the citation guarantee (clause IDs, §4.1 item 4)
   and the QWK-cliff check. Keep rules close to the guide's wording, because L2 and L3 were fitted to dev and test
   has more news and fda_label items.
2. **Shared work.** The clause splitter and trimmer (§4.1 item 1) serve the model's pointers, the demo's quotes and
   the rules' spans. Widening to the full clause was tried and failed (E008); trimming to about 8 words is the open
   lead.
3. **One dev check, no tuning sweep.** Score rules + model on dev once, behind a fixed conservative gate. Keep the
   model on the test items if composite doesn't drop by more than 0.02 and added aspects are right at least 60% of
   the time (break-even is about 0.4, E018). Otherwise the model runs on transcripts only.
4. **Only if Sunday has slack:** the PubMed direction × outcome-goodness rule (research report B, pick 1), then the
   hedge cap (B, pick 4). Log one row each.

**Protocol:** follow `../CLAUDE.md`. Read the log before trying anything, score with `src/eval/score_dev.sh` or
`score.py --items data/dev.full.jsonl`, and log every run with `src/eval/log_exp.py`.

---

## 6. Tavily and Exa (bonus points), scoped to 22 hours

Neither tool is called at scoring time. `grep -rE 'tavily|exa' src/inference` must come back empty. Budgets, rules
R1–R9 and the ledger follow `RESEARCH_README.md`. **No test-item text ever goes into a query.**

| Priority | Job | Tool | Output |
|---|---|---|---|
| **Must** | Trial → NCT → product → phase for A, B and rivals | **Exa Agent** (`effort: medium`, `outputSchema`; one run each for A, B and rivals) | `research/knowledge/trials.json`, `rivals.json`, used by rules and cards |
| **Must** | Regulator, HTA, payer and guideline bodies with speaker roles; dated event timeline 2025-01 to 2026-10 | **Tavily search** (basic, `--topic news`, date bounds) | `bodies.json`, `timeline.json` |
| **Must** | Live-mode demo: fresh public items labeled by the local model | **Tavily search** → item JSON → `/analyze` | One demo moment (§8) |
| Done | Open-source research for targets A–D (10 Tavily Research mini runs, the full cap) | Tavily Research, Tavily search/extract, Exa MCP | `research/reports/{A,B,C,D}-*.md` |
| Should | Market, PV and compliance facts for the pitch | Taken from research report D; check each against its primary source | Cited slide facts |
| Should | "Expand this signal" on a card | **Exa** find-similar | Related coverage, labeled locally |
| Could | Rare-class augmentation corpus | Tavily map → extract, plus Exa find-similar | `research/corpus/<class>/`, deduped against test |

Every knowledge-pack entry keeps its source URL, so the UI can show where the background knowledge came from.
Live mode is opt-in, and the air-gap toggle turns it off.

**Exa Agent needs an API key** in `~/.config/exa/key`, which doesn't exist yet. Without it, build the trial
tables with Tavily search and the Exa MCP tools.

---

## 7. The startup

> **Superseded by `STARTUP.md`** (Sat 2026-11-07 evening): analog-launch comparison (mobocertinib), private
> transcripts labeled offline, and Tavily/Exa as the per-drug setup engine. The text below is the earlier draft.

**Working name:** Signal-to-Dose. Run one Tavily search for name conflicts before putting it on slides.

**One line:** On-prem launch intelligence for pharma brand teams. It turns the noise around a launch into cited,
actionable signals and sentiment trends, and no data leaves your walls.

**Who buys:** brand and launch teams, medical affairs, market access and CI at mid-size and large pharma, starting with
oncology launches.

**Why us:**
- **Compliance blocks cloud LLMs** for confidential field notes, advisory-board transcripts and MSL insights. A small
  model on the customer's own box removes that objection. **It runs on a laptop**: the demo is a MacBook with the
  network off.
- **Pharmacovigilance hook.** Adverse-event mentions in listening data may trigger reporting duties. The safety
  flag with an exact quote works as AE triage.
- **Trust from citations.** Every score traces back to a verbatim quote. No quote, no claim.
- **Domain sense.** Generic listening tools don't know what "MARIPOSA OS" or "NICE rejected on cost" means for a brand plan.

**Tiers:**
1. *Public Pulse*: public sources plus live monitoring through Tavily and Exa.
2. *Private Signals*: the customer's own transcripts and field notes, fully offline. This is the transcript judging criterion as a product.
3. *Launch Room*: weekly brief, alerts and export.

The 2B is the laptop tier. A 9B on the same pipeline is the higher-accuracy server tier.

**Business model:** annual licence per brand, on-prem or in the customer's VPC. Show the measured cost per 100 items against a frontier-API equivalent.

**Moat:** the launch-signal ontology, per-therapeutic-area fine-tunes, and the provenance and compliance layer.

**Rule:** no unsourced numbers on slides. Market, PV and compliance facts come from research report D
(`research/reports/D-pharma-listening-pv.md`), each checked against its primary source. The Tavily Research reports
got licences and numbers wrong, so never cite them directly.

---

## 8. The demo UI

**Stack:** FastAPI serving precomputed JSON plus a live `POST /analyze`, and a single-page frontend. Everything is
served from localhost, and the final demo runs on the Mac.

| Priority | Screen |
|---|---|
| **P0** | **Signal feed.** Cards sorted by actionability, then recency, with signal chip, product badge, headline, why it matters, confidence and citation chips. A citation opens the source with the quote highlighted and a "verbatim ✓" badge. Filters by product, signal and actionable. |
| **P0** | **Sentiment trends.** Weekly lines per aspect on a −2 to +2 axis, with product toggle, speaker filter and shift markers. Clicking a point shows the quotes behind it. |
| **P0** | **Analyze.** Paste text or a **transcript** and get labels, highlighted spans and a card from the local model, with latency, cost per 100 items and a **network: OFF** indicator. |
| P1 | **This week.** Top 3 signals, biggest sentiment moves and new risks, each cited. |
| P1 | **Under the hood.** Dev scorecard (rules vs model), model profile, Tavily/Exa provenance and spend. |
| P2 | Heatmap (aspect × speaker), live-mode panel, Exa expand. |

**Demo script (about 4 minutes):**
1. Hook (20s): a launch-week question.
2. Feed (60s): the top card, clicked through to the verbatim quote.
3. Trends (60s): one real shift, with the quotes behind it.
4. Air-gap (45s): network off, paste a mock advisory-board transcript, get cards and sentiment from the local 2B.
   An HCP's mention of a patient's side effect lights up the AE triage flag.
5. Live mode (30s): network on, Tavily pulls a fresh item, and the local model labels it.
6. Startup close (25s).

Pick the hero storyline **after** the corpus is labeled, from what the data actually shows.

---

## 9. Repo layout and interfaces

```
hack1984/                      ← repo root (CLAUDE.md, CONCEPTS.md, docs/)
  drug track/
    PROBLEM.md  DATA.md  RESEARCH_README.md
    analysis/                  ← profiling, early baselines (exists)
    src/
      rules/predict.py         ← rules-only predictor, levels 1–3 (exists)
      eval/                    ← score_dev.sh, log_exp.py (exists)
      inference/               ← offline core: normalize, rules, model client, span builder, guards, merge
      aggregate/               ← trends + cards
      train/                   ← teacher labeling, dataset build, LoRA (cut under decision 8)
      live/                    ← Tavily/Exa connectors (online only)
    config/models.yaml         ← profiles: qwen35-2b (default), qwen35-9b (standby)
    research/                  ← ledger.jsonl (exists), knowledge/, raw/, reports/
    models/<profile>/          ← GGUF + adapter (gitignored)
    app/                       ← FastAPI + frontend
    out/                       ← gitignored: dev/, labels/, submission.jsonl, trends.json, cards.json
    run_offline.sh             ← items in → submission + labels + trends + cards out, network off
```

**Contracts, so the UI can start right away on rules-only output:**
- `out/labels/{dev,test,unlabeled}.jsonl`: item fields (`item_id, source, url, published, product, title, text`) plus
  label fields (`signal_type, actionable`, the five aspects) plus `meta: {by: "rules-L3" | "<profile>", confidence}`.
- `out/trends.json`:
  `{series: [{product, aspect, speaker, week, mean, n, quotes: [{item_id, span, polarity}]}], shifts: [{product, aspect, speaker, week, delta}]}`.
- `out/cards.json`:
  `[{card_id, published, product, signal_type, actionable, headline, why, confidence, citations: [{item_id, url, span}]}]`.
- `POST /analyze {text, title?, source?}` → `{labels, card, latency_ms}`. A `source` of `transcript` (or none) takes the model path.

---

## 10. Team, schedule and milestones (DRAFT, to discuss)

**Proposed roles:**

| Who | Owns |
|---|---|
| **North: pipeline** (on the Mac) | Toolchain check, rule engine, clause splitter and trimmer, model path, span builder, guards, eval and log, transcript path, cost per 100 items, `submission.jsonl`, `run_offline.sh` |
| **Teammate 2: app and demo** | Aggregator (trends and cards), FastAPI app, P0–P2 screens, AE triage badge, demo script, final integration on the Mac |
| **Teammate 3: research and pitch** | Tavily/Exa knowledge pack and ledger, 2–3 mock transcripts (ACI-Bench / PriMock57 turn format, invented people), primary-source checks of the pitch facts, live-mode connector, pitch deck |

**Draft schedule (EST), lean plan:**

| Time | Pipeline (North) | App (T2) | Research and pitch (T3) |
|---|---|---|---|
| Sat 14:30–15:00 | **All three:** agree the lean plan, roles and §9 contracts | | |
| 15:00–17:00 | Mac toolchain check · rules L3 → `out/labels/*` for all 2,033 items · **safety-net `submission.jsonl`** · clause splitter and trimmer | App scaffold on the rules labels · aggregator v0 | Knowledge pack (Tavily search + Exa MCP) · mock transcripts |
| 17:00–20:00 | Model path v0: clause-ID pointers, transcripts first, then PubMed/news/press gaps · guards · AE triage rules | Feed + trends + quote drill-down | Pitch facts checked against primary sources · slide draft |
| **20:00 G1** | **One dev check:** rules + model vs rules alone. Keep the model on test items if composite doesn't drop by more than 0.02 and added aspects are right at least 60% of the time; otherwise transcripts only | | |
| 20:00–23:00 | Transcript path end to end · cost per 100 items · `run_offline.sh` v0 | Analyze screen against the Mac's `/analyze` · AE triage badge · this-week brief | Live-mode connector · slides |
| 23:00–06:00 | The Mac labels the full corpus with the chosen pipeline. Team sleeps (shifts to be agreed) | | |
| Sun 06:00–08:30 | Final `submission.jsonl` · slack items if any (§5 item 4) | UI on final data · under the hood | Demo script and slides final |
| **09:00** | **Code freeze** · `run_offline.sh` with the network off (incl. a transcript) · package code and weights | Move the UI onto the Mac | Rehearse |
| 09:30–10:30 | **All three:** rehearse twice, fix only blockers | | |
| **10:30** | **Submit** (30 minutes of buffer) | | |

**Milestones:**

| # | Milestone | Target | Done when |
|---|---|---|---|
| M0 | Safety net | Sat 17:00 | Valid rules-only `out/submission.jsonl` (240 lines) and `out/labels/*` exist |
| M1 | Toolchain verdict | Sat 17:00 | Qwen3.5-2B loads and grammar-decodes on the Mac, throughput measured, or the fallback model is chosen |
| M2 | Knowledge pack | Sat 20:00 | `research/knowledge/*.json`, checked against primary sources, loads offline |
| M3 | Model v0 + G1 | Sat 20:00 | Rules + 2B scored once on dev and logged. Zero-shot 9B only if the Mac is idle |
| ~~M4~~ | ~~Silver labels~~ | — | Cut (proposed, decision 8) |
| M5 | Transcripts end to end | Sat 23:00 | `/analyze` handles a mock transcript on the Mac, with speaker roles and the AE triage flag |
| ~~M6~~ | ~~LoRA~~ | — | Cut (decision 8) |
| M7 | Final labels | Sun 08:30 | Final submission, plus corpus labels, trends and cards from the chosen pipeline |
| M8 | Offline proof + freeze | Sun 09:30 | `run_offline.sh` passes with the network off. Package ready |
| M9 | Submitted + rehearsed | Sun 10:30 | Everything handed in. Demo rehearsed twice |

**Already cut (decision 8):** LoRA, teacher labels and the silver hold-out (proposed), the score-tuning
experiments, the augmentation corpus. **Cut order if time runs short:** 9B zero-shot → Exa expand / live-mode
extras → heatmap → this-week brief → AE triage badge in the UI (keep it in the pitch). **Never cut:** M0 safety
net, the citation guarantee, the transcript path, M8 offline proof.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| The model scores below rules on dev | Rules win where they fire. The model only fills abstentions and transcripts (G1) |
| Rules are overfitted to dev (L2 and L3 were fitted to dev) | Accepted under the lean plan: with no silver hold-out we can't measure it. Keep rules close to the guide's wording |
| QWK cliff | Pre-submit check that matched polarities are varied. See the solutions doc |
| Private transcripts differ from the training items | Turn splitting, a speaker-from-turn mapping (Dr./MD → hcp, patient → patient, payer/PBM → payer), mock transcripts in dev testing |
| The 2B breaks JSON or invents spans | Grammar-constrained decoding with the schema also in the prompt, clause-ID pointers, the span builder |
| Qwen3.5 unsupported by MLX or llama.cpp | M1 check, with Qwen2.5-3B as fallback |
| One shared Mac is a bottleneck | Only the pipeline needs it until integration. The UI builds on JSON. Overnight, the Mac labels the full corpus |
| Judges' hardware is unknown | GGUF that runs on CPU, pinned `requirements.txt`, one-command `run_offline.sh` |
| Test leakage | Never design from test, never send test to the teacher or a search, dedupe any harvested corpus (R6) |
| The 3B rule changes | Switch `MODEL_PROFILE` to `qwen35-9b` |
| The deadline slips | Safety-net submission from M0. Freeze at 09:00. Submit at 10:30 |

---

## 12. Definition of done

- [ ] `out/submission.jsonl`: 240 lines, valid, every span an exact substring, matched polarities not all one value
- [ ] Final dev score logged in `../docs/experiments/log.md`
- [ ] `run_offline.sh` passes with the network off, on test items and a mock transcript
- [ ] UI runs from localhost on the Mac, with trends from about 2,000 items labeled by our pipeline
- [ ] Ledger, knowledge-pack provenance and leftover Tavily/Exa budget documented
- [ ] Cost per 100 items measured and shown
- [ ] Code, model name plus adapter or GGUF, and README handed in
- [ ] Pitch: problem, product, why on-prem, PV hook, business model, demo

---

## 13. Open questions for the planning discussion

1. **Where does the model earn its place?** *Answered by decision 8:* it owns transcripts first, and fills
   aspects the rules miss only if the one dev check at G1 passes (composite doesn't drop by more than 0.02, and
   added aspects are right at least 60% of the time).
2. **Spans:** *Answered:* the model points at a clause ID and code does the quoting. Clauses score 0.673 span F1
   against 0.395 for sentences on dev, and research report C found free-text quotes are exact only 64–73% of the
   time.
3. **Fine-tuning in 22 hours:** *Answered by decision 8:* no LoRA.
4. **Encoder classifiers** for signal and actionable (`DATA.md` §7.2): cut for time? Proposed yes.
5. **Teacher:** *Proposed cut (decision 8).* Does anyone on the team want it kept, for example to measure how
   much the dev-fitted rules drop on test-like items?
6. **Transcripts:** what format do we expect, and what is the speaker mapping? Who writes the mock transcripts
   (invented people only)? Should we ask the organisers what "private transcripts" look like?
7. **Roles and sleep:** names for T2 and T3, whether they agree with the split, and the overnight shift plan.
8. **Handing in:** how do the judges want code and weights delivered (repo link, download, Docker)? Which runtime
   do we ship (llama.cpp GGUF vs MLX)? Ask the organisers.
9. **Demo story:** which trend to lead with. Decide after M7 from the real data.
