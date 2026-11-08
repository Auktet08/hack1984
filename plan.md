# Signal to Dose project plan

**Status as of Nov 8, 2026, 03:40 Eastern**  
**Working branch** `lean-plan` (nothing committed this session)  
**Goal** Improve the offline drug-signal labeler while preserving a verified 240-row submission and an offline transcript path.  
**Deadline** Devpost submission closes 2 hours before hacking ends.

## Current release (v2, candidate F)

The active submission is [submission.jsonl](drug%20track/out/submission.jsonl), SHA-256 `f2b24304…`. The v1 file is kept as [submission.v1-hybrid.jsonl](drug%20track/out/submission.v1-hybrid.jsonl) for rollback.

| | v1 hybrid | **v2 (F)** |
|---|---:|---:|
| Silver holdout composite (105 test-like items, Gemini labels) | 0.6328 | **0.7103** (99.9% paired wins, 95% CI of gain +0.028 to +0.148) |
| Dev composite (60 gold) | 0.8460 | **0.8648** (77% paired wins; within dev noise) |
| Dev human-reviewed (15) | 0.864 | 0.829 (more matched aspects, weaker quotes) |
| Holdout aspect F1 / signal macro-F1 / actionable F1 | 0.22 / 0.33 / 0.67 | 0.75 / 0.44 / 0.76 |

What v2 adds on top of v1, all local and loopback-only on the base Qwen3.5-2B GGUF:
- **L4 rules** learned from the silver pool: cost-effectiveness titles → access_pricing; "review" titles are not expert_opinion; safety+efficacy titles → efficacy; drug-information news pages → none.
- **Linear heads on Qwen embeddings**, trained on 1,030 Gemini silver items: aspect presence, sentence locator, actionable (threshold 0.3), and a ridge quote scorer with lexical features, which keeps quotes at gold-like length.
- **Qwen scoring:** a 5-point polarity rating of the chosen sentence with logistic calibration and expected-value rounding; zero-shot signal for news, and for press releases where the rules say efficacy; item-level safety yes/no stacked into the safety presence head.
- **Cue rules:** press/news safety and convenience, PubMed cost-study access_cost, and fda_label safety/convenience (discontinue, withhold, prophylaxis, every-4-week schedule).

Reproduce with `drug track/run_v2.sh data/test_inputs.full.jsonl out/submission.jsonl`. It needs base-GGUF loopback servers on 18080 (chat) and 18090 (`--embedding --pooling mean`); commands are in the script header. A cold-cache rerun matches 239/240 rows; the other row has one borderline polarity (−1 vs 0) from llama.cpp float noise. Transcripts still use `run_offline.sh --transcripts` with the base GGUF; that code is unchanged.

[Release manifest](drug%20track/out/submission_manifest.json) · [Experiment log rows E056–E062](docs/experiments/log.md) · code in `drug track/src/v2/`

## What has been done

| Area | Completed work and result |
|---|---|
| Local runtime and data | Restored the organizer abstracts and verified dev and test text hashes. Installed MLX and llama.cpp. Verified local schema-constrained inference. Trained a 120-step general LoRA and fixed the MLX-to-GGUF normalization and convolution layout conversion. The corrected export agreed with native MLX on 8 of 10 initial parity cases, so release scoring used the exact Q8 runtime. |
| Offline pipeline | Added the evidence splitter, local model client, rules merge, resumable cache, offline runner, submission validator, and dev/silver scoring tools. Verified the original 240-row run with external networking blocked and only loopback model access. |
| Evidence and polarity diagnostics | Full sentences contained the reference span in 10/10 missed dev efficacy cases versus 4/10 for short windows. Polarity direction was correct on 12/13 with the reference sentence versus 10/13 with Qwen's selected sentence. Broader retrieval improved shortlist coverage from 4/10 to 10/10 on eligible dev and from 16/33 to 32/33 on eligible silver. These are gold-assisted retrieval diagnostics. |
| Initial efficacy candidates | Whole-sentence prompting, explicit attribution rules, and a second model verifier each failed the release gate. The initial 12-step specialist pilot improved a synthetic contrast set from 2/10 to 4/10, with one of five complete pairs correct. |
| Extended training | Completed two 240-step evidence-ID runs and a 180-step sentence-level run. The first specialist scored 0.8226 on dev with 2/12 exact additions. The cleaner specialist scored 0.8286 with 5/16 exact additions, and improved the provisional public audit from 5/13 to 8/13. Its attribution-filtered variant scored 0.8344 with 3/8 exact additions. The sentence-level GGUF abstained on all eligible dev items at the fixed margin. On 34 internal validation items, the selected sentence checkpoint got 16/34 in MLX and 12/34 in GGUF. |
| Audit material | Froze 13 public pre-2025 PubMed abstracts with provisional labels, 11 wrong-target counterfactual pairs based on those abstracts, two neutral comparison examples, and three case/distractor examples. The first training pool had related study IDs across splits. The cleaner training recipes excluded explicit shared NCT IDs. The public audit is separate from adapter training and its labels still need independent review. |
| Curated specialist | Completed a **300-step** one-sentence LoRA run on **144** training examples. The data include reviewed training excerpts, observed-outcome contrasts, and examples of results attributed to a different treatment. Step **240** has the lowest saved validation loss (**0.235**). Export and outcome evaluation are pending. |

[Experiment log](docs/experiments/log.md) · [Extended run notes and artifacts](drug%20track/out/refinement/continuation/notes.md) · [Original one-hour refinement plan](docs/plans/2026-11-07-one-hour-model-refinement.md)

## Session of Nov 8 (00:45–03:40): what was tried

| Idea | Result |
|---|---|
| Curated 300-step sentence specialist (step 240) | Zero additions anywhere. MLX and GGUF agree; the answer-token distribution is near-flat. The low validation loss came from template tokens (E056). |
| Proper full-JSON distillation LoRA | Abandoned: about 7.5 s/step at 900 tokens on this Mac (8 layers), so 1.5–3 h per epoch. |
| Embedding heads + L4 + LLM polarity/signal + cue rules | Kept: E057 → E058 → E059 → E060 → **E062 (promoted)**. |
| LLM multiple-choice and yes/no location re-ranking | No gain over the embedding locator (about 60% top-1). |
| Question-conditioned last-token embeddings | No gain. |
| LoRA yes/no cross-encoder for location (1,000 steps) | Location +4–5 points, but the full pipeline was not better (E061). |
| Joint cross-sentence quote scorer, LLM actionable stacking, polarity blending, abstract context for polarity, news speaker rules, stacked PubMed signal classifier, adding dev gold to training | Each neutral or worse on the holdout and/or dev. |

Key measurement lesson: Rules L3 is heavily fitted to dev (holdout aspect F1 0.22 vs dev 0.62). Tune on 5-fold out-of-fold silver pool (`src/v2/cv.py`, `tune.py`), and confirm on the silver holdout plus dev.

## What still needs to be done

1. **Upload the release to Devpost** before the cutoff (2 hours before hacking ends): `drug track/out/submission.jsonl`, which is v2 F.
2. **Check transcript and demo behavior** with both servers running, and confirm the startup/demo flow still points at the base GGUF.
3. **Commit the v2 code** (`drug track/src/v2/`, `run_v2.sh`, plan, log) once the user approves. Inspect the incoming `origin/lean-plan` commits first; the local branch was seven commits behind.
4. **Remaining levers, if time allows:** sentence location (about 60%) caps quote F1 and polarity on matched aspects. Holdout signal macro-F1 (0.44) is limited by rare PubMed classes. News speaker attribution is always "media".

## Overall approach

Keep the strongest validated pipeline as the baseline. Improve one behavior at a time, beginning with high-precision efficacy additions. Diagnose retrieval, attribution, and polarity separately, then test a frozen candidate on dev, the teacher-labeled holdout, and a fresh audit. Judge the result with the organizer scorer, raw correctness counts, evidence inspection, and exact offline runtime validation. The release decision for this session is made: v2 F is promoted, with v1 kept for rollback.
