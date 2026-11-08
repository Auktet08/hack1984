# The Signal-to-Dose labeler: model and training

This file describes the system that produced the submission (`out/submission.jsonl`, release v2, candidate F, 2026-11-08). It covers what the model is, how it was trained, how well it scores and how to rerun it with the network off.

## In one paragraph

Everything runs offline on one open model, **Qwen3.5-2B** (2.27B parameters, under the track's 3B cap). It is served locally by llama.cpp and is never allowed past loopback. The pipeline has four layers:

1. **Rules** taken from the labeling guide.
2. **One LoRA fine-tune** of Qwen, which picks the signal type for PubMed items.
3. **Small linear classifiers trained on Qwen's own text embeddings.** These find the aspects, choose the sentence and quote for each aspect, and decide whether an item is actionable.
4. **The base Qwen answering short multiple-choice questions.** It rates sentiment, picks the signal type for news and press releases, and confirms whether an item discusses safety.

All learned parts were trained on 1,038 public items labeled by a frontier "teacher" model (Gemini). No test item was ever sent to a hosted model or used to design rules.

## What it outputs

For each item the system gives:
- the signal type (efficacy, safety, regulatory, competitor move and so on);
- whether a launch team should act on it;
- for each of five aspects (efficacy, safety, convenience, access/cost, evidence quality): a sentiment from −2 to +2, the speaker, and a quote copied exactly from the text.

## Training data

| Set | Items | Labels | Used for |
|---|---:|---|---|
| Dev | 60 | organizer gold | final check only (the rules were written against it, so it flatters them) |
| Silver pool | 925 | Gemini teacher | training and 5-fold cross-validated tuning |
| Silver holdout | 105 (60 PubMed, 30 news, 15 press) | Gemini teacher | confirming changes; it looks like test |
| Test | 240 | none | producing the submission only |

**How the silver labels were made** (`silver/README.md`):
- The teacher was `gemini-3.8-flash` at temperature 0, with JSON output enforced by the API's schema.
- Its prompt held the full labeling guide plus 3 dev examples from the same source.
- Every quote was checked against the item text. 1,064 matched exactly, 14 were repaired and 57 were dropped.
- On dev the teacher scores 0.876, against 0.843 for the rules. It finds far more aspects (49 vs 25 of 56), but its quotes are less precise.

**Why the holdout matters:** the rules score 0.843 on dev but only 0.623 on the silver holdout, where they find just 14 of 114 aspects. Dev alone would have hidden that, so every change below had to win on the holdout and the cross-validated pool and stay level on dev.

## The fine-tune: signal LoRA (v1)

**Setup:** trained with MLX on a MacBook (Apple M6, 24 GB), using a 4-bit conversion of `Qwen/Qwen3.5-2B` (revision `15852e8c…`).

| Setting | Value |
|---|---|
| Method | LoRA, rank 8, scale 20, dropout 0, on the last 4 layers |
| Optimizer | Adam, learning rate 1e-4, batch size 1, 120 steps, seed 1984 |
| Sequence length | 1,152 tokens, with gradient checkpointing |
| Loss | answer tokens only (`--mask-prompt`) |
| Data | 834 train / 33 validation chat examples (`src/train/make_lora_data.py` → `out/lora_short/`) |
| Example | a short prompt holding the item's text; the answer is the teacher's JSON label (signal, actionable, aspects with quotes) |
| Validation loss | 0.180 at step 40, 0.236 at step 80, 0.176 at step 120 (step 120 shipped) |

**Constraints:** full fine-tuning and longer contexts ran out of memory. Unquantized training at 4,096 tokens and 4-bit at 3,072 tokens both failed, which is why the context is short and the adapter small.

**Export to llama.cpp:**
1. Fuse the adapter, dequantized, with `mlx_lm.fuse`.
2. Undo two MLX storage conventions (RMSNorm weights stored +1, transposed convolution kernels) with `src/train/restore_qwen_hf_layout.py`.
3. Convert to Q8_0 GGUF (`models/qwen35-2b-lora-v1.q8_0.gguf`).

The GGUF matched MLX on 8 of 10 dev examples. Scoring always uses the GGUF that ships.

**What the fine-tune is trusted with:** the adapter predicts every field, but only its **signal type** passed the gate:
- With the organizer guide in the prompt, its signal type won 99.1% of paired resamples on the holdout, and 3 of its 5 changes on dev were right (log row E034).
- Its aspects, sentiment and quotes lowered the overall score (E029–E033), so those come from the other layers.

### Further fine-tunes that were tried and rejected

| Attempt | Result |
|---|---|
| Clinical-response specialists (teacher, filtered and attribution-checked data; 180–240 steps) | Small gains on dev that failed the holdout and audit gates (E047, E051, E054, E055) |
| Curated one-sentence specialist (rank 8, 4 layers, 300 steps) | Changed nothing. Its low validation loss came from template tokens, and its answer distribution was nearly flat (E056) |
| Yes/no sentence cross-encoder (rank 16, 8 layers, 1,000 steps, 3.5k pairs) | Found the right sentence more often (holdout 60% → 63%), but sentiment got worse and the overall score didn't improve (E061) |

**Lesson:** at about 7.5 s per step for 900-token inputs, LoRA on this Mac is too slow and too small to beat a frozen model with trained heads. Check answer-token accuracy directly, not validation loss.

## The v2 layers on top (trained, but Qwen's weights unchanged)

**Embeddings.** The base Qwen serves mean-pooled embeddings on port 18090. Each item, sentence and candidate quote is embedded once and cached.

**Classifiers on embeddings** (`src/v2/heads.py`, scikit-learn). In the release these are fit on all 1,030 silver pool and holdout items.

| Classifier | Model | Input | Decision |
|---|---|---|---|
| Aspect present? (one per aspect) | logistic regression | item embedding | above 0.5 |
| Which sentence carries the aspect | logistic regression | sentence embedding + TF-IDF + position and section features | highest score |
| Actionable | logistic regression | item embedding | above 0.3 |
| Which quote within the sentence | ridge regression, alpha 3 | embedding + TF-IDF cue words, small length penalty | highest score |

The quote scorer mattered more than expected. Teacher quotes are about 7–8 words, and without the lexical features it picked whole sentences. Adding them raised quote overlap in the right sentence from 0.48 to 0.59 on the holdout and 0.64 on dev. Headers such as "CONCLUSIONS:" are stripped from quotes.

**Base Qwen as a scorer** (`src/v2/llm_feats.py`). The 2B model is never asked to write JSON. It answers one-letter questions, the probabilities of the answer letters are read, and a small logistic layer turns them into a decision.

| Question | Calibration | Result |
|---|---|---|
| Sentiment of the chosen sentence on an aspect (A–E = −2…+2) | logistic regression on the letter probabilities + aspect + source, fit on teacher quotes | about 81% exact on teacher quotes. The release rates the whole sentence (sentiment agreement 0.60 → 0.67 on the holdout) and rounds the expected value, which suits the sentiment metric best |
| Main signal type (9 options) | none (zero-shot) | used for news, and for press releases the rules call efficacy. Holdout signal F1 rose from 0.33 to 0.44 |
| Does the item discuss safety? (yes/no) | stacked with the safety classifier | separates items with and without safety content almost perfectly (AUC 0.95–0.99) |

**Rules learned from the silver pool** (`src/v2/rules4.py`, `heads.py`). These were written from the pool, not from dev or test:
- cost-effectiveness papers get the access/pricing signal and an access/cost aspect;
- titles about efficacy outcomes override a safety signal;
- drug-information pages get signal "none";
- FDA label changes get safety and convenience aspects (10 of 10 correct on silver and dev);
- cue words add safety and convenience aspects for press releases and news.

**Order of the layers:**
1. Rules L3.
2. The LoRA signal.
3. The pool rules.
4. The classifiers fill the aspects the rules leave empty and choose sentences and quotes.
5. Base Qwen rates sentiment and settles signal type for news and press releases.

The full configuration is `out/v2/policy-f.json`.

## Results

The overall score is the mean of seven parts: signal F1, actionable F1, aspect F1, sentiment agreement, speaker accuracy, quote overlap and citation validity.

| Version | Silver holdout (105) | Dev (60) |
|---|---:|---:|
| v1: rules L3 + signal LoRA | 0.633 | 0.846 |
| + embedding aspect classifiers and pool rules (E057) | 0.657 | 0.855 |
| + Qwen sentiment, quote scorer, actionable classifier (E058) | 0.678 | 0.867 |
| + zero-shot news/press signal (E059) | 0.695 | 0.868 |
| + cue and label rules, expected-value sentiment (E060) | 0.709 | 0.864 |
| **+ safety stack (E062, released)** | **0.710** | **0.865** |

**How much to trust the gains:**
- **Holdout:** v2 beats v1 in 99.9% of paired resamples, and the gain's 95% interval is +0.028 to +0.148.
- **Dev:** v2 wins 77% of paired resamples. At ±0.055 noise that alone proves little.
- **Citations:** every one of the 240 test rows passes the citation check, since all quotes are copied exactly from the item text.
- **Human-reviewed dev subset (15 items):** v2 scores 0.829 vs 0.864 for v1. It finds 13 of 14 aspects instead of 9, but quotes some of the new ones less precisely.

These figures use classifiers fit on the 925-item pool. The release classifiers also include the 105 holdout items.

## Known limits

- **Finding the right sentence** is right about 60% of the time. It is the main cap on quote overlap and sentiment agreement.
- **The silver labels are Gemini's, not gold**, so silver scores measure agreement with the teacher.
- **Reruns from empty caches** match 239 of 240 rows. In the other row a borderline sentiment flips between −1 and 0 because of llama.cpp floating-point noise.
- **Private transcripts** go through the original base-model path (`run_offline.sh --transcripts`), not v2.

## Running it offline

Run from `drug track/`. Start two loopback servers from the base GGUF:

```bash
llama-server -m models/qwen35-2b-base.q8_0.gguf --jinja --host 127.0.0.1 --port 18080 -c 8192 --parallel 1 --cache-ram 0
```

```bash
llama-server -m models/qwen35-2b-base.q8_0.gguf --embedding --pooling mean --host 127.0.0.1 --port 18090 -c 8192 -b 4096 -ub 4096
```

Then produce and check the submission. `run_v2.sh` runs inside a macOS sandbox that denies all network access except loopback.

```bash
./run_v2.sh data/test_inputs.full.jsonl out/submission.jsonl
```

```bash
python3 src/inference/check_submission.py data/test_inputs.full.jsonl out/submission.jsonl
```

**Retraining:**
- The classifiers: `out/mac/venv/bin/python src/v2/predict_v2.py fit --policy out/v2/policy-e.json --heads out/v2/heads-e-all.pkl --include-holdout`.
- The signal LoRA: follow `MAC_CHECK.md` (training and GGUF export).
- The LoRA's signal labels for test are frozen in `out/submission.v1-hybrid.jsonl`, which the policy reads.

**Weights (SHA-256 in `out/submission_manifest.json`):**
- base `models/qwen35-2b-base.q8_0.gguf` (from `unsloth/Qwen3.5-2B-GGUF`, revision `f6d5376b…`);
- LoRA `models/qwen35-2b-lora-v1.q8_0.gguf`;
- classifiers `out/v2/heads-e-all.pkl`;
- safety stack `out/v2/presence-stack-safety-pool.pkl`.

Every experiment, kept or rejected, is a row in `docs/experiments/log.md`. The evaluation lessons are in `docs/solutions/best-practices/silver-holdout-over-dev-and-local-llm-scoring.md`.
