# Local model: the full process, from teacher labels to shipped GGUF

**Updated:** Sat 2026-11-07, 17:45 EST, by North (pipeline owner). **Status:** stage 1 is done, and the teacher
labels are pushed to GitHub (`drug track/silver/`, branch `lean-plan`). Stage 2 is under way: the Mac owner is
running Qwen3.5 on Ollama. Stages 3–8 are to do.
**Goal:** Fine-tune our local model (Qwen3.5-2B, within the 3B cap) on labels from a frontier "teacher" model (Gemini).
Then use the local model alongside the rules **only where it measurably helps** the hidden-test score and the
network-off transcript run.
**Hard deadline:** Sun 2026-11-08, 11:00 EST, for everything. Score work freezes **Sun 06:00**, code freezes **09:00**.

> **New here? Start with this file.** It is meant to be enough on its own. For background, see:
> `drug track/README.md` and `drug track/LABELING_GUIDE.md` (the task; these win over this plan) ·
> `drug track/DATA.md` (data and scorer facts) · `docs/experiments/log.md` (**the only results table**; read
> "Decisions in force") · `CONCEPTS.md` (vocabulary: aspect, matched aspect, composite, QWK cliff).
>
> This plan **replaces** the model units (U4, U5 and U7) of `docs/plans/2026-11-07-1536-feat-score-lift-plan.md`.
> Its gate (KTD2), merge order (KTD7) and trimmer rules (KTD8) still apply and are repeated here.

> **🖥️ Mac check: the next blocker. Mac owner, please do this now.**
> - Qwen3.5 already runs on Ollama, but that doesn't finish the check.
> - We still need `drug track/MAC_CHECK.md` **steps 0, 1, 2 and 3** (step 3 is the LoRA test, the most important),
>   the GGUF conversion test, and the **Results table** filled in and sent to North.
> - The Ollama JSON test below replaces MAC_CHECK step 4.
> - Exact list: the "Mac check checklist" in stage 2 (§4). It takes about 40 minutes, and everything after stage 2
>   depends on it, including the 22:00 go/no-go for training.

---

## 0. The whole process on one page

| # | Stage | Where it runs | Status | Output |
|---|---|---|---|---|
| 1 | **Teacher labels.** Gemini labels the 1,038 unlabeled pubmed, news, press and fda_label items | laptop → Gemini API | ✅ **done** (17:15) | `drug track/silver/unlabeled_gemini.checked.jsonl` (in git; local copy in `out/teacher/`) |
| 2 | **Toolchain check.** The 2B loads, decodes JSON, trains a LoRA, and converts to GGUF | Mac | 🟡 **in progress:** Qwen3.5 runs on Ollama. LoRA and GGUF not yet checked | MAC_CHECK results table |
| 3 | **Split.** Teacher labels → a test-shaped hold-out (about 105 items) and a training pool (about 925) | laptop | to do | `out/silver/` |
| 4 | **Clauses.** Number every clause with character offsets. The model's answers point at these numbers | laptop | to do | `src/inference/clauses.py` |
| 5 | **Model client and zero-shot baseline.** The 2B with no training, run behind the rules | laptop + model server | to do | dev and hold-out scores (the bar to beat) |
| 6 | **LoRA data.** Teacher labels → chat-format training rows that point at clauses | laptop | to do | `out/lora_data/` |
| 7 | **Train** overnight | Mac | to do (go/no-go 22:00) | `out/adapters/v1` |
| 8 | **Gate and ship.** Keep only what wins, then fuse, convert to GGUF and submit | laptop + Mac | Sun 05:00–09:00 | `out/submission.jsonl`, GGUF |

```
 unlabeled items ──► [1] Gemini teacher ──► silver labels ──► [3] split ──► hold-out (scoring only)
                                                                    └──────► training pool ──► [6] LoRA rows ──► [7] train
                                         [4] clauses ──────────────────────────────┘                                  │
 item ─► clauses ─► rules L3 (keep what they set) ─┬─► 2B (+LoRA): {signal, actionable, aspects:[{unit_id, aspect, polarity}]}
                                                   └─► merge (rules win, model fills gaps) ─► quote = clause text, trimmed ─► guards ─► label
```

---

## 1. Why we do it this way

- **The headroom is aspects.** The rules-only predictor (L3) scores **0.843** dev composite, but finds only 25 of 56 gold
  aspects (aspect F1 0.617). Perfect PubMed fields would add up to +0.114 (E019). PubMed is 104 of the 240 test items.
- **The teacher is good at exactly that.** Gemini scored aspect F1 **0.870** on dev (E021) against the rules' 0.617.
- **Distillation works at this scale.** In LA-ABSA, a sub-1B student trained on teacher labels reached 49.85 F1, against
  51.10 for the teacher itself. EHSAN found that LLM-only labels lose under 0.02 F1 against human-reviewed ones
  (`drug track/research/reports/A-span-grounded-absa.md`, pick 4).
- **Citations must be exact substrings.** A 2B quoting free text is exact only 64–73% of the time (report C). So the
  model returns a **clause number**, and code copies the clause. Citation validity is 1.0 by construction.
- **Small models need evidence first.** Put `unit_id` before `aspect` and `polarity` in the JSON, and keep the schema text in the prompt as
  well as in the grammar. A grammar alone cost a 2B 6 of 20 answers (report C, pick 3).
- **Transcripts need a model anyway.** The judges run private transcripts with the network off, and the rules do nothing on them.

---

## 2. Rules everyone follows

1. **Test is off limits.** Never open `drug track/data/test_inputs*.jsonl` except to run the final predictor. Never
   send it to Gemini or a search. `gemini_label.py` refuses any file whose name contains "test".
2. **Log every scored run, kept or not:**
   `python3 "drug track/src/eval/log_exp.py" --score <score.json> --change "..." --verdict kept|reverted|info --note "..."`
3. **Dev is noisy (±0.055 at 95%).** A change under 0.02 is noise; say so in the note. No sweeps of thresholds, prompts or learning rates.
4. **The organisers' files are read-only and never committed:** `README.md`, `LABELING_GUIDE.md`, `data/`, `scoring/`, `tools/`,
   `sample_submission.jsonl`.
5. **`drug track/out/submission.jsonl` is always valid.** Replace it only with a configuration that passed the gate (stage 8).
   Keep the previous file as `submission.prev.jsonl`.
6. **Python standard library only** outside the model server and MLX. Tests use `unittest` (pytest isn't installed).
7. Outputs go under `drug track/out/` (gitignored). Code goes under `drug track/src/`, and tests under `drug track/tests/`.

**Already tried or ruled out, so don't redo them** (see the log):
- self-consistency voting
- the 9B model
- threshold or prompt sweeps
- the NLI aspect detector
- expected-value polarity decoding
- retrieved few-shot
- encoder classifiers
- labelling the whole corpus with the model
- widening rule spans to the full clause without a trimmer (E008)

---

## 3. Stage 1: teacher labels ✅ done

### What we ran

`drug track/src/teacher/gemini_label.py` sends one prompt per item:
- a fixed header (one JSON object, spans copied character for character from one sentence, no tools);
- the **full `LABELING_GUIDE.md`**, rulings included;
- **3 dev examples with gold labels from the same source**, preferring ones that have aspects, and never the item itself;
- the item.

Replies are cached in `<out>.raw/`, so a rerun only retries failures. Token use goes to `<out>.stats.json`.

```bash
cd "drug track"
# key: GEMINI_API_KEY or ~/.config/gemini/key
python3 -I src/teacher/gemini_label.py --items data/unlabeled.full.jsonl \
  --sources pubmed,news,press_release,fda_label --backend api --thinking low --model gemini-3.8-flash \
  --out out/teacher/unlabeled_gemini_api_low.jsonl --jobs 8 --timeout 120 --retries 4
```

- **Backend:** direct REST API, schema-constrained JSON, temperature 0, `thinkingLevel: low`.
- **Not labelled:** ctgov and fda_event. The rules handle those almost deterministically, and the model won't run on them.

### Calibration on dev first (log rows E020–E022)

| Run | Dev composite | Human-15 | Aspect F1 | Signal mF1 | Actionable F1 | QWK | Span F1 | Time for 60 items |
|---|---|---|---|---|---|---|---|---|
| Rules L3 (E009) | 0.843 | 0.864 | 0.617 | 0.856 | 0.762 | 0.933 | 0.731 | — |
| Gemini CLI, high thinking (E020) | 0.882 | 0.838 | 0.878 | 0.962 | 0.769 | 0.909 | 0.695 | ~40 min |
| Gemini API, low thinking (E021) | 0.874 | 0.854 | 0.870 | 0.911 | 0.769 | 0.960 | 0.622 | 33 s |
| E021 + span check (E022) | 0.876 | 0.854 | 0.860 | 0.911 | 0.769 | 0.960 | 0.632 | no new calls |

- **API with low thinking was chosen.** It is within noise of the CLI and about 70× faster.
- **Caveat:** the few-shot examples come from dev, which flatters the dev score a little.

### Span check (built into the script)

Each teacher span is checked in this order:
1. exact match;
2. normalised match (case, quotes, spaces);
3. fuzzy repair inside one sentence at ≥ 80% cover;
4. otherwise the aspect is dropped.

The raw file is `…api_low.jsonl`. **Use the checked file `…api_low.checked.jsonl`.**

### Result

- **1,038 / 1,038 labelled, 0 failed.** Run time was about 10 minutes at 8 parallel jobs.
- **Tokens:** 4.9M input (0.48M cached), 0.12M output, no thinking tokens.
- **Spans:** 1,135 aspects in total. 1,064 were exact, 2 were repaired by normalising, 12 by fuzzy match, and **57 dropped (5%)**.

| Source | Items | Items with no aspect | Aspects per item | Aspects | Top signals | Actionable yes |
|---|---|---|---|---|---|---|
| pubmed | 896 | 342 | 1.04 | efficacy 404, evidence_quality 277, safety 218, access_cost 26, convenience 6 | efficacy 643, safety 114, none 80, access_pricing 23, expert_opinion 20 | 79 |
| news | 96 | 38 | 0.78 | efficacy 50, safety 9, evidence_quality 7, access_cost 5, convenience 4 | efficacy 37, none 19, regulatory 10, access_pricing 8, expert_opinion 7, competitor_move 7 | 45 |
| press_release | 38 | 3 | 1.63 | efficacy 30, safety 21, convenience 8, access_cost 3 | efficacy 22, regulatory 7 | 32 |
| fda_label | 8 | 1 | 1.25 | safety 7, convenience 3 | regulatory 7 | 7 |

- **Polarity mix:** −2: 3 · −1: 495 · 0: 60 · +1: 417 · +2: 103.
- **Span length:** median 7 words, max 30. Texts are 1,708 characters at the median, 2,981 at p95 and 8,881 at most.
- **Products:** A 870, B 84, both 84.

### How we treat these labels (decision)

The old plan wanted the teacher at 0.90 dev composite or more before trusting silver labels. It reached 0.874–0.882. Its
span F1 (0.632) looks lower than the rules' (0.731), but that comparison is misleading. Span F1 is averaged only over
**matched** aspects, and the teacher matches 49 against the rules' 25:

- On the **24 aspects both of them match**, the teacher quotes better: 0.789 vs 0.747.
- The gap comes from the **25 harder aspects only the teacher finds** (span F1 0.480 on those). Those aspects were
  worth 0 before.

Of the teacher's 49 matched dev quotes:

| Exact | Partial overlap | Too long (contains gold) | Too short | A different sentence for the same claim |
|---|---|---|---|---|
| 19 | 12 | 11 | 2 | 5 |

Separately, on the unlabeled run, **5% of aspects were dropped** because the quote wasn't in the text at all
(paraphrased, or taken from the title).

The student doesn't copy the teacher's quotes: it points at a clause, and code quotes it. The teacher's quote only
decides **which clause**, which is why stage 6 uses the overlap rule it does.

So:
- the labels **train** the model (aspect, polarity, signal, actionable);
- the silver hold-out is a **second** yardstick for **model** changes only, never used to remove rules;
- dev stays the primary score.

### Deeper evaluation of the teacher (log row E023)

Measured on the 60 dev items, using the checked teacher file:

| | Aspect precision | Aspect recall | Extra aspects | Missed aspects | Polarity exact | Speaker |
|---|---|---|---|---|---|---|
| Gemini low + span check | 0.84 | **0.88** | 9 | 7 | 47/49 | 49/49 |
| Gemini CLI, high thinking | 0.92 | 0.84 | 4 | 9 | 41/47 | 45/47 |
| Rules L3 | 1.00 | 0.45 | 0 | 31 | 23/25 | 25/25 |

- **Teacher minus L3, paired bootstrap** (2,000 resamples): +0.035, with a 95% interval of −0.006 to +0.080. It's
  better in 94% of resamples. That's likely better, but not significant on 60 items.
- **By source** (teacher vs L3, aspects matched of gold):

  | Source | Teacher | L3 |
  |---|---|---|
  | PubMed | 28/31 | 13/31 |
  | Press release | 7/10 | 1/10 |
  | News | 3/4 | 1/4 |
  | fda_label | 1/1 | 0/1 |
  | fda_event | 10/10 | 10/10 |

- **A hybrid** (L3 on ctgov and fda_event, the teacher elsewhere) scores 0.874, the same as the teacher alone, so
  the teacher already handles the rule-driven sources.
- **Weak spot 1: evidence_quality.** It matched 4 of 8, added 4 extras, and caused 4 of the 7 misses. It's also the
  vaguest aspect in the guide.
- **Weak spot 2: efficacy on preclinical studies and case reports** where gold has none (PM-0043, PM-0090, PM-0028).
  Ruling 2 says to fill efficacy only when the text judges our product.
- **Some "extras" are gaps in gold.** NW-0008's "No new safety signals were identified" was labeled safety 0, which
  is ruling 8, but gold has it blank.
- **Polarity:** one sign flip and two cases one step too strong (+1 → +2). Everything else is exact.

**The rules are probably overfitted to dev.** Teacher-vs-L3 agreement falls from dev to unlabeled items on the
same sources:

| Source | Signal type, dev → unlabeled | Aspect agreement (F1), dev → unlabeled |
|---|---|---|
| PubMed | 0.88 → 0.73 | 0.51 → 0.31 |
| News | 0.60 → 0.40 | 0.33 → 0.15 |
| Press release | 1.00 → 0.74 | 0.22 → 0.41 |

The teacher wasn't fitted to dev and L3 was, so the likeliest reading is that **L3 scores below 0.843 on test**,
mostly on PubMed and news (134 of the 240 test items). Stage 3's "L3 on silver hold-out" row measures this
directly. It's also why the possible gain from the model on test is probably bigger than E018's +0.025 on dev.

**What to expect from the student:** probably between L3 (0.843) and the teacher (0.876) on dev. That's a guess
until stage 8 measures it. The student will copy the teacher's weak spots (evidence_quality, efficacy on
preclinical studies), so watch those aspects in the stage 8 per-group check.

### Leakage check

- No unlabeled text in this run is identical to a test text.
- **All 8 fda_label items share a URL with a test item** (other sections or versions of the same drug label). Measured
  by word overlap (Jaccard, numbers only, no test content read), 7 of them are different text (0.17–0.32).
- **One is a near-duplicate: `U-FDA-00488`.** It has the same section title as a test item, a different label date and
  a word overlap of 0.91. Training on it would give the model frontier labels for what is in effect a test item.
  Stage 3 drops it, along with any other near-duplicate the general rule finds.

---

## 4. Stages 2–8

Owners: **[Model]** = whoever owns the model work (North by default). **[Mac]** = whoever has the MacBook.
Each stage has a "done when". Don't start a stage until the stages it depends on are done.

### Stage 2. Toolchain check + conversion test [Mac] (about 40 min, start now)

**Status at 17:45:** the Mac owner is running Qwen3.5 on **Ollama**. The `MAC_CHECK.md` results table is still
empty. What that settles and what it doesn't:

| Check | Settled by Ollama? | What's still needed |
|---|---|---|
| (a) The 2B loads and decodes JSON | **Partly.** Qwen3.5 runs on this Mac. Ollama is built on llama.cpp, so a Qwen3.5 GGUF also works | Confirm the **2B** tag: `ollama list` should show e.g. `qwen3.5:2b`, not a larger default. Note its quantisation (e.g. Q4_K_M). Test JSON with a schema in `format` on `/api/chat`, plus `"think": false`. Get speeds from `ollama run <tag> --verbose` |
| (b) A LoRA trains | **No.** Ollama can't train | `MAC_CHECK.md` step 3 with `mlx-lm`, on the Hugging Face weights `Qwen/Qwen3.5-2B` (not Ollama's GGUF) |
| (c) fuse → GGUF → serve | **No** | The commands below. Ollama can serve the result instead of llama-server: a Modelfile with `FROM ./fused_test.q8_0.gguf`, then `ollama create hack-test -f Modelfile`. Merge the adapter into the model first; don't rely on Ollama's `ADAPTER` line, which may not support Qwen3.5 |

Ollama also has an OpenAI-compatible endpoint (`http://localhost:11434/v1/chat/completions`), so it can be the
stage 5 model server: set `MODEL_URL` to it. Two things to watch:
- **Quantisation.** Ollama's default tag is usually 4-bit. Score the zero-shot baseline and the LoRA with the same
  quantisation you ship, or the stage 8 comparison is unfair. Q8 is safest.
- **Chat template.** Ollama applies its own template from the Modelfile. It must match the template the LoRA was
  trained with (stage 6), including the empty `<think></think>` block.

#### Mac check checklist (`drug track/MAC_CHECK.md`, with Ollama already running)

Every test uses made-up sentences. No hackathon data goes on the Mac for this check.

| MAC_CHECK step | Still needed? | Why |
|---|---|---|
| **0.** What machine is this | ✅ **Yes** (2 min) | Chip, RAM and disk decide batch size and max sequence length for stage 7 |
| **1.** Install `mlx-lm` + llama.cpp | ✅ **Yes** | Ollama doesn't include `mlx-lm`, and training needs it |
| **2.** Run the 2B with MLX, thinking off | ✅ **Yes** | Training runs on the MLX copy (Hugging Face weights), not Ollama's GGUF, so the MLX copy must load too |
| **3.** 10-step LoRA fine-tune + adapter loads | ✅ **Yes, the most important** | It's check (b). If it fails, there's no LoRA for Qwen3.5 (see §6) |
| **4.** llama.cpp with JSON-only output | ⏭️ **Replaced by the Ollama JSON test below** | Ollama is built on llama.cpp and already serves the model |
| **5.** Fallback model | Only if step 2 or 3 fails | Qwen2.5-3B-Instruct |
| **Two questions** (overnight availability) | ✅ **Yes** | Stage 7 needs the Mac plugged in and awake 22:00–05:00 |
| **GGUF conversion test** (numbered step 2 below) | ✅ **Yes** | It's check (c). Run it right after step 3, on that step's 10-step adapter |
| **Results table** | ✅ **Fill it in and send it to North** | Add the Ollama tag, quantisation and speeds in the "Fallback / notes" row |

**Ollama JSON test** (replaces MAC_CHECK step 4; use the 2B tag `ollama list` shows):

```bash
ollama list                                   # note the tag (must be 2B) and the quantisation
ollama run qwen3.5:2b --verbose "Say hi"      # note prompt eval rate and eval rate (tokens/s)
curl -s http://localhost:11434/api/chat -d '{
  "model": "qwen3.5:2b", "stream": false, "think": false,
  "format": {"type": "object",
             "properties": {"aspect": {"type": "string", "enum": ["efficacy", "safety"]},
                            "polarity": {"type": "integer"}},
             "required": ["aspect", "polarity"]},
  "messages": [{"role": "user", "content":
    "Return aspect and polarity (-2..2) for: \"Osimertinib significantly improved progression-free survival.\""}]
}'
```

**Pass:** the reply's `message.content` is valid JSON matching the schema, with no `<think>` text.

1. Run `drug track/MAC_CHECK.md` steps 0–3 and the Ollama JSON test, as in the checklist above. Fill in its
   Results table and send it to North.
2. **Most important:** prove that a LoRA can become a GGUF *before* we train a real one. Use the fake adapter from
   MAC_CHECK step 3:
   ```bash
   cd ~/hack1984-check && source .venv/bin/activate
   mlx_lm.fuse --model Qwen/Qwen3.5-2B --adapter-path lora_adapter --save-path fused_test
   git clone --depth 1 https://github.com/ggml-org/llama.cpp ~/llama.cpp
   pip install -r ~/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
   python ~/llama.cpp/convert_hf_to_gguf.py fused_test --outtype q8_0 --outfile fused_test.q8_0.gguf
   llama-server -m fused_test.q8_0.gguf --jinja --port 8081 -c 8192   # then rerun the step-4 curl against :8081
   ```
3. Note the seconds per training iteration and the peak memory from step 3.

**Done when:** we know three things:
- (a) the 2B loads and decodes JSON;
- (b) a LoRA trains;
- (c) fuse → GGUF → llama-server works.

**If (c) fails:** we can still ship MLX (`mlx_lm.server` is OpenAI-compatible), but only for the Mac. Tell North at once.
**If (a) or (b) fails:** use `Qwen/Qwen2.5-3B-Instruct` everywhere below (MAC_CHECK step 5).

### Stage 3. Hold-out + training pool [Model] (about 45 min)

1. Write `drug track/src/eval/make_silver.py` with a fixed seed, reading `unlabeled.full.jsonl` and the checked teacher file:
   - **Drop near-duplicates of test:** any item whose word-set Jaccard with any test text is ≥ 0.8. Today that drops only
     `U-FDA-00488`. Print only the IDs and scores, never test text. This is the one permitted read of test, as in the
     dedupe step of the old plan.
   - **Hold-out (105 items, shaped like test):** pubmed 60, news 30, press_release 15, stratified by product. Never used for
     training, few-shot or validation. fda_label stays out of the hold-out: 7 items are too few to measure anything.
   - **Training pool:** the rest, about pubmed 836, news 66, press_release 23, fda_label 7.
   - Writes `out/silver/holdout.full.jsonl` + `holdout.gold.jsonl` and `out/silver/pool.full.jsonl` + `pool.gold.jsonl`.
     `full` holds the item fields; `gold` holds the teacher labels in submission format, so `score.py --gold` accepts it.
2. Write `drug track/src/eval/compare.py`. It scores two prediction files against the same gold, with 1,000 paired bootstrap
   resamples, and prints both composites, the mean gain and the share of resamples where the gain is above 0.
3. Score L3 on the hold-out and log an `info` row ("L3 on silver hold-out"). This is the first measure of how much the
   dev-fitted rules drop on test-shaped items.

**Tests (`drug track/tests/test_make_silver.py`, `test_compare.py`):**
- The same seed gives the same IDs.
- No ID is in both sets, and `U-FDA-00488` is in neither.
- Per-source counts match the targets.
- Comparing a file with itself gives a gain of 0.

**Done when:** the files exist, the tests pass and the row is logged.

### Stage 4. Clause splitter and trimmer [Model] (about 1.5 h, parallel with stage 3)

`drug track/src/inference/clauses.py` provides `split(text) -> [{id, start, end, text}]` and `trim(clause_text, n=14)`.
- **Sentences first,** never across `…` or `[...]`.
- **Then clauses:** split on `, ; : — (`, and before "that", wh-words and subordinating conjunctions. Split on "and"/"or" only when
  both sides have **3 or more words**, so "safety and efficacy" stays whole.
- **Press releases:** headlines and navigation runs are their own units (split on line breaks).
- **Offsets:** `text == item_text[start:end]`, always.
- **Trim:** at most N = 14 words, with trailing punctuation stripped (the scorer keeps punctuation on tokens). Try one alternative,
  N = 8, once. No sweep.
- **Measure:** best-clause span F1 on the 46 dev free-text gold aspects (target ≥ 0.673; the whole sentence gets 0.395), and log an
  `info` row.

**Tests (`drug track/tests/test_clauses.py`):**
- On every dev item, every clause is an exact substring at its offsets.
- "Osimertinib improved PFS, which was consistent with prior data" splits before "which".
- An empty text gives no clauses.
- Text containing `…` never gives a clause that crosses it.

### Stage 5. Model client, merge and the zero-shot baseline [Model] (about 2.5 h, needs 2(a) and 4)

Files: `drug track/src/inference/model.py`, `merge.py`, `predict_full.py`, plus `tests/test_model_parse.py` and `tests/test_merge.py`.

1. **The server is a URL.** `MODEL_URL` (default `http://localhost:8080/v1/chat/completions`) points at an OpenAI-compatible
   llama-server, either the Mac's or North's laptop (RTX 3050 Ti, 4 GB, fits a Q8 2B). Ollama works too:
   `http://localhost:11434/v1/chat/completions`. Check once that it honours `response_format` and turns thinking off.
   If it doesn't, call Ollama's native `/api/chat` with `format` and `"think": false`.
2. **Two prompt styles, chosen with `--prompt`:**
   - `full` (zero-shot): the guide section for the source, 2–3 dev examples from the same source (never the item), the
     JSON schema written out, and the numbered clauses.
   - `short` (for the LoRA): a 3-line instruction, then source, product, title and the numbered clauses. No guide and no
     examples. A short prompt is several times cheaper per item, and cost per 100 items is judged.
3. **Output schema, evidence first:**
   `{"signal_type", "actionable", "aspects": [{"unit_id", "aspect", "polarity"}]}`, with `unit_id` an enum of this item's
   clause IDs. Send it as `response_format` json_schema **and** write it in the prompt. Thinking is off
   (`chat_template_kwargs: {"enable_thinking": false}`), temperature 0. Strip code fences and `<think>` before parsing.
4. **Failures and caching:** on a parse failure or timeout, the model gives nothing for that item, and the rules' output stands.
   Cache replies by prompt hash under `out/model_cache/`.
5. **Merge (KTD7):** rules keep every field they set. The model fills null aspects. When its flag is on, the model may override only
   `actionable: no` and the default PubMed/news `efficacy` signal. The flags are `--model-aspects`, `--model-signal` and
   `--model-actionable`, all off by default.
   - **Speaker** comes from the source table in `src/rules/predict.py` (`SPEAKER`). The model never predicts it.
   - **Span** = the trimmed clause text.
6. **Guards:** polarity is clipped to ±1 unless an L3 strong cue is in the clause. fda_event is capped at −1.
7. **Baseline runs:** run rules + zero-shot 2B on dev and on the hold-out, one flag at a time. Log a row each.

**Tests:**
- An unknown `unit_id` is dropped.
- A reply wrapped in a code fence parses.
- If the rules set safety and the model does too, the rules' value stays.
- With all flags off, output is byte-identical to rules L3.

**Done when:** a full dev run has a parse failure rate under 5%, and the zero-shot rows are logged. Zero-shot is the bar the
LoRA must beat.

### Stage 6. LoRA training data [Model] (about 1.5 h, needs 3 and 4)

`drug track/src/train/make_lora_data.py` writes `out/lora_data/{train,valid}.jsonl` in MLX chat format:
`{"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}`.

- **Input:** the stage 5 `short` prompt, built by the **same function** `model.py` uses. Import it; don't copy it.
- **Target:** the stage 5 schema, filled from the teacher label. For each teacher span:
  - Pick the clause that shares the most words with it.
  - Measure overlap as **the share of the clause's words that appear in the teacher span**, not the reverse. Teacher
    quotes are often longer than one clause (11 of 49 on dev contained the whole gold quote). Measured the other way,
    a long but correct quote would be dropped.
  - **Drop the aspect if that share is under 0.5.**
  - If over 20% are dropped, fix the splitter before training.
- **Keep items with no aspects** (342 PubMed items have none). The model must learn to abstain, because a wrong extra aspect costs more than a miss
  (polarity, speaker and span are scored only on matched aspects).
- **Rebalance:** repeat news and press_release rows ×2. Test has 30 news and 18 press items, against 66 and 23 in the pool.
  That gives about 1,010 rows.
- **Validation:** `valid.jsonl` is 5% of the **pool** (not the hold-out), used only for loss curves.
- **Chat template:** render one row with the tokenizer's `apply_chat_template` and check that it matches what llama-server sends
  at inference, including any empty `<think></think>` block.
- **Report:** row count, token-length p50/p95/max (texts reach 8,881 characters, so check that the max fits `--max-seq-length`),
  and the share of rows with aspects.

**Tests:**
- A span that is exactly one clause maps to that clause.
- An overlap under 0.5 is dropped.
- No hold-out ID appears in the output.
- The prompt is identical to `model.py`'s for the same item.

### Stage 7. Train overnight [Mac] (smoke test 21:30, go/no-go 22:00, run 22:00 → about 05:00)

```bash
caffeinate -dims &
mlx_lm.lora --model Qwen/Qwen3.5-2B --train --data out/lora_data \
  --batch-size 4 --num-layers 16 --learning-rate 1e-4 --max-seq-length 3072 \
  --mask-prompt --grad-checkpoint --iters <N> --steps-per-report 10 --steps-per-eval 50 \
  --save-every 100 --adapter-path out/adapters/v1
```

- **Smoke test first:** 20 iterations. Check that the loss falls, and that the adapter loads and returns valid JSON on 5 dev items.
- **Choose `N`:** about 2 epochs, which is about 2 × 1,010 ÷ 4 ≈ 500 iterations. Cap it so the run ends by 05:00 at the measured seconds per
  iteration. `--save-every 100` means a crash still leaves a usable checkpoint.
- **If memory runs out:** use `--batch-size 2` and `--max-seq-length 2048`, and truncate long clause lists in stage 6.
- **One run.** Don't sweep learning rate or rank.

**Go/no-go at 22:00. All of these must be true:**
- stage 2 (a) and (b) passed;
- stage 6 produced at least 600 rows;
- the smoke test passed.

The zero-shot result does **not** block training: the LoRA may fix what zero-shot gets wrong. It is judged in stage 8.

### Stage 8. Gate and ship (Sun 05:00–09:00) [Model + Mac]

**Gate (05:00–06:00).** Serve the adapter and run rules + LoRA (`--prompt short`) on dev and the hold-out, one flag at a time, in this order:
**aspects → signal → actionable**. Each group is judged against the configuration that already holds the earlier kept groups.
Keep a group only if **both** of these are true:
- **Silver:** the gain over the current kept configuration is positive in **≥ 80%** of 1,000 paired resamples (`compare.py`).
- **Dev:** composite drops by **no more than 0.02**, and at least 60% of the items or aspects the group changes are right against
  dev gold.

Compare three systems: L3 alone, L3 + zero-shot and L3 + LoRA. Pick the best one that passes, and log a row for every run.
**Score work freezes at 06:00.**

**Ship (06:00–08:30):**
1. **Fuse and convert** the kept adapter to `models/qwen35-2b-lora/…q8_0.gguf` (the stage 2 commands).
2. **Parity check:** run 10 dev items through MLX and through the GGUF. The labels should match on at least 9 of 10. If they don't,
   the GGUF or the chat template is off, so ship the version you scored.
3. **Submission:** run the kept configuration on the test inputs locally, then `src/inference/check_submission.py`:
   - 240 lines;
   - every span is an exact substring;
   - predicted polarities aren't all one value.

   Swap `out/submission.jsonl` only if it passes.
4. **Transcripts:** run the mock transcripts through the LoRA and through the base model. If the LoRA does worse (it was trained
   on abstracts and news), route `source=transcript` to the base GGUF and ship both GGUFs (about 2.5 GB each).
5. **Offline proof:** run `run_offline.sh` with the network off.
6. **Cost:** measure cost per 100 items with the short and the full prompt.

---

## 5. Timeline (EST)

| Time | Model owner | Mac holder |
|---|---|---|
| Sat 17:20–18:45 | Stage 3 (split, compare) · stage 4 (clauses) | **Mac check:** `MAC_CHECK.md` steps 0–3, the Ollama JSON test and the GGUF test, then send the Results table to North |
| 18:45–21:00 | Stage 5 (client, merge, zero-shot on dev + hold-out) · stage 6 (LoRA rows) | Serve the 2B for stage 5 · stay available |
| 21:30 | Smoke-train 20 iterations | |
| **22:00** | **Go/no-go** | Start the full run under `caffeinate` |
| 22:00–05:00 | Sleep | Mac trains. Check the loss once around 01:00 if awake |
| Sun 05:00–06:00 | **Stage 8 gate**, log rows | |
| **06:00** | **Score freeze** | |
| 06:00–08:30 | Ship | Fuse, GGUF, parity check |
| **09:00** | Code freeze | |

---

## 6. If things go wrong

| Problem | What to do |
|---|---|
| The Mac can't run Qwen3.5-2B | Qwen2.5-3B-Instruct everywhere (MAC_CHECK step 5) |
| Qwen3.5 runs on Ollama but `mlx_lm.lora` fails on it | No LoRA for Qwen3.5. Either ship zero-shot Qwen3.5 on Ollama, or try the LoRA on Qwen2.5-3B, which mlx-lm supports well. Decide at 22:00 |
| Ollama is serving a non-2B tag or a 4-bit quantisation | Pull the 2B tag and use Q8 for every scored run (3B cap; stage 8 needs a fair comparison) |
| The LoRA scores well in MLX but worse through Ollama | It's almost always the chat template or the quantisation. Rerun the stage 8 parity check with the Modelfile `TEMPLATE` set to match training |
| Fuse → GGUF fails | Ship MLX with `mlx_lm.server`, say so in the README, and ask the organisers about runtime (PROBLEM.md §13 Q8) |
| The Mac is unavailable tonight | No LoRA. Ship zero-shot if it passed the gate on its own, otherwise rules only. North's laptop can serve the 2B GGUF |
| Parse failures above 5% | Check that the schema is in the prompt and the fences are stripped. Try grammar off once (report C pick 3). Nothing more |
| More than 20% of teacher aspects don't map to a clause | Fix the splitter (it is too coarse or too fine), not the threshold |
| The LoRA loses to zero-shot or rules | Revert and log it. The submission stays as it was. That is a fine outcome |
| Time runs out | Cut in this order: the cost figure → the actionable group → the signal group. Never cut: a valid submission, the citation guarantee, the network-off run |

---

## 7. Files and commands

| What | Path |
|---|---|
| Teacher labeller | `drug track/src/teacher/gemini_label.py` |
| Teacher labels (use these) | **In git:** `drug track/silver/unlabeled_gemini.checked.jsonl` (+ `.raw.jsonl`, `.stats.json`, `README.md`). Local original: `drug track/out/teacher/unlabeled_gemini_api_low.checked.jsonl` (raw cache in `.raw/`) |
| Teacher on dev | **In git:** `drug track/silver/dev_gemini.checked.jsonl` + `.score.json`. Local: `drug track/out/teacher/dev_gemini_api_low.checked.jsonl` |
| Rules predictor | `drug track/src/rules/predict.py --level 3` |
| Score rules on dev | `"drug track/src/eval/score_dev.sh"` |
| Score any predictions | `python3 -I "drug track/scoring/score.py" --gold <gold.jsonl> --pred <pred.jsonl> --items <items.full.jsonl>` |
| Log a run | `python3 "drug track/src/eval/log_exp.py" --score <score.json> --change "..." --verdict ... --note "..."` |
| Unit tests | `python3 -m unittest discover -s "drug track/tests"` |
| Mac runbook | `drug track/MAC_CHECK.md` |
| Research behind the design | `drug track/research/reports/A-span-grounded-absa.md` (pick 4: silver-label recipe), `B-clinical-claim-polarity.md`, `C-grounded-extraction.md` (picks 3–4: schema, trimmer) |
| Lessons | `docs/solutions/best-practices/` (QWK cliff, matched-only metrics, oracle headroom) |

**New files these stages create:**
- `src/eval/make_silver.py` and `src/eval/compare.py`
- `src/inference/clauses.py`, `model.py`, `merge.py`, `predict_full.py` and `check_submission.py`
- `src/train/make_lora_data.py`
- a test file for each, under `drug track/tests/`

---

## 8. Open questions

1. **Who has the Mac** for stages 2 and 7, and can it stay plugged in and awake 22:00–05:00?
2. Does a teammate take stage 3 or 4 so they run in parallel, or does North do all the [Model] stages?
3. Judges' runtime: GGUF (runs on CPU anywhere) or MLX? Ask the organisers. It decides stage 8 if the conversion fails.
   **Ollama is now a third option.** It serves the same GGUF, and judges install one app instead of building
   llama.cpp. It's probably the easiest for a network-off run if the organisers allow it.
4. **Mac owner, please report:** the Ollama tag and quantisation (`ollama list`), the prompt and generation speeds
   from `--verbose`, and whether `mlx-lm` is installed for step 3.
