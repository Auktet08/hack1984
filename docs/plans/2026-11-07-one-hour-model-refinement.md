# Signal to Dose one-hour autonomous refinement plan

**Branch** `lean-plan`  
**Scope** Offline Qwen3.5 2B and Rules L3. Improve the classification pipeline within one wall-clock hour and retain a reproducible release candidate only if it earns promotion.  
**First target** Blank PubMed efficacy labels where the abstract reports an observed outcome attributable to Tagrisso, Rybrevant, or Lazcluze. Start with documented patient response, disease control, and progression after treatment. Existing signal, actionability, and populated aspect decisions are outside this candidate's edit scope.

## Starting point and why this hour is different

The shipped hybrid scores **0.8460** on 60 dev items and **0.6328** on the 105-item Gemini-labeled silver holdout. The guided Qwen adapter supplies eligible signal overrides. Rules L3 supplies actionability and aspects. Keep the exact shipped predictions as the comparison baseline. The default in `gate_local.py` builds a Rules L3 baseline, so use its scorer and paired comparison helpers with the saved hybrid predictions, or add explicit baseline arguments before using its CLI.

| Prior result | What it changes about the next experiment |
|---|---|
| Re-rating Qwen's own quote got 8/13 correct. The reference quote got 9/13. | Measure evidence availability and direction separately on the same examples. One extra correct answer gives little basis for choosing between them. |
| The sentence prompt emitted an efficacy label on 21/21 eligible dev items and 58/58 eligible silver items. | Make abstention an explicit output choice and test whether the model can use it before doing a full run. |
| The tight lexical filter accepted two correct dev labels and zero silver labels. | Measure how many genuine outcomes enter and survive candidate selection. Broaden clinical evidence retrieval while keeping the acceptance standard. |
| Base Qwen's support check accepted 2/21 proposals and one polarity was correct. | A second opinion on the same quote already failed. Give each stage a specific, separately measurable job. |
| The corrected Q8 export matched MLX on 8/10 parity examples. | Evaluate any new adapter in the actual GGUF runtime before considering release. |

[Experiment log](../experiments/log.md) · [Local model runbook](../../drug%20track/MAC_CHECK.md)

## Research translated into experiments

- **Bind the drug, outcome, and direction.** Span-based aspect sentiment research treats the relation between the target and the opinion span as its own prediction problem. For this task, a treatment mention and a survival result anywhere in the same abstract are weak evidence. Retrieve a unit that contains the treatment and the outcome, or resolves the treatment through the immediately preceding sentence. Keep the final citation within one source sentence. This is an adaptation of the research design to our task. [Span-level aspect sentiment extraction](https://aclanthology.org/2021.acl-long.367/) · [SciFact](https://aclanthology.org/2020.emnlp-main.609/)
- **Test attribution and abstention directly.** Use paired examples that change one important fact. Swap target and comparator, turn an observed result into a study objective, and change response to progression. Change formatting alone for an invariance control. Count complete pairs that pass and track false acceptance among unsupported claims. [CheckList](https://aclanthology.org/2020.acl-main.442/) · [Contrast sets](https://aclanthology.org/2020.findings-emnlp.117/)
- **Measure the trade-off between coverage and errors.** Record how many additions a candidate makes, how many are correct, and what it abstains on. Choose any margin threshold on development data and freeze it before holdout evaluation. Where the installed llama.cpp build exposes usable label scores, probe a short label alphabet and check that the codes are single tokens in context and scores are comparable. A score masked by the grammar or a model-written confidence number is insufficient for calibration. [SelectiveNet](https://proceedings.mlr.press/v97/geifman19a.html) · [Contextual calibration](https://proceedings.mlr.press/v139/zhao21c.html) · [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- **Improve the supervision before spending the hour on training.** Inspect high-disagreement training cases for wrong-drug teacher labels and evidence alignment failures. The current builder can omit an aspect when its quote cannot be aligned to a unit. Audit those omissions before treating blank targets as examples of abstention. A later specialist adapter can train on verified positive, neutral, negative, and unsupported examples with compact evidence units. Quantized adapter training reduces memory demand, and the existing MLX recipe is the local starting point. [Dataset Cartography](https://aclanthology.org/2020.emnlp-main.746/) · [QLoRA](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1feb87871436031bdc0f2beaa62a049b-Abstract.html) · [MLX LoRA documentation](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)

## The 60-minute run

### 00–07 minutes · Reproduce and lock the comparison

- Record the branch, checkout revision, working-tree status, submission SHA-256, Q8 artifact hash, and runtime version. Work alongside existing local changes. Use a fresh directory under `drug track/out/refinement/` and record a fixed seed, prompt hash, dataset IDs, and output filenames.
- Reproduce the dev and silver scores from `out/review/lora-guide-signal-dev.jsonl` and `out/review/lora-guide-signal-silver.jsonl` with the organizer scorer. Assert exact ID coverage and the expected baseline scores before evaluating changes. If prediction files are missing, restore them with the exact runbook command or stop release evaluation and use available artifacts for diagnostics.
- Check the adapter endpoint on loopback port 18083 and the base endpoint on 18080. Make a short structured-output smoke call and measure it. If recovery takes more than three minutes, use the cached output and CPU-only controls while leaving time for the audit and report.
- Freeze the change scope and release criteria below. Use the existing frozen splits. The training-data builder reads test inputs for deduplication, so build any pilot data from the existing exported training pool and validation split without rerunning the full splitter.

### 07–17 minutes · Find where usable evidence is lost

- On eligible dev items, compare candidate units from the current eight-word windows, a full sentence, and a two-sentence context window with separate citation offsets. Count gold-quote containment and best token-overlap F1 for each. Record when the treatment and observed outcome can be resolved in each unit. Gold-assisted measurements are diagnostic upper bounds.
- Evaluate direction on the same cases under two inputs where time permits. Supply the gold sentence in one condition and the selected sentence in the other, holding the model, prompt, and output format fixed. Record direction sign and exact five-point polarity separately. A direction error changes the finding itself. A magnitude error changes its strength.
- Freeze six to twelve synthetic contrast cases, in pairs, with expected outputs and document groups. Include target/comparator reversal, a result rewritten as an aim, drug response versus procedure recovery, observed patient progression versus cellular resistance, and capitalization or punctuation invariance. Freeze these before candidate inference. Keep the previous five-item spot check for regression context. If a genuinely fresh public audit set with verifiable provenance is already available, label a small sample before viewing predictions and keep it out of training and prompts. Record assistant judgments as provisional and report any lack of independent review.

### 17–32 minutes · Build one narrow challenger

**Default design** Rank evidence by the co-occurrence of target aliases and broad clinical outcome cues. Include observed response, disease control, time to progression, survival, and follow-up language. Allow adjacent context for attribution and negation. Keep original offsets through normalization. Evaluate a cheap control that selects evidence without Qwen, using the same acceptance checks. This tests whether a model call adds value.

- If the evidence audit shows poor coverage, improve the candidate units and ranking before changing polarity. Capture a candidate's treatment anchor, outcome anchor, and source offsets. Preserve the comparator when it determines direction.
- If usable evidence is usually available but polarity or abstention fails, ask for a short closed choice on the top evidence units. Use `unsupported`, `favorable`, `neutral`, and `unfavorable`. Make `unsupported` distinct from neutral. A supported output must identify an evidence unit and cite a literal contiguous source span that supports the direction for the target. Use the guide's magnitude rules to produce the final five-point value. Use short label scoring only if the preflight established that scores are available and interpretable. Otherwise use a constrained enum with a first-class abstain choice.
- Hold other inputs fixed. Compare the challenger to the shipped hybrid, the existing sentence proposal, and the CPU control on dev. Log eligible items, retrieval misses, treatment or comparator errors, unsupported emissions, sign errors, magnitude errors, quote overlap, and latency. Reject wrong-target or unverifiable spans. Avoid treating source or abstract title alone as attribution.
- If there is one concentrated failure with a clear fix, make **one** revision and rerun dev. Examples include adding adjacent context for resolved treatment references, or using separate outcome spans when a sentence describes two drugs. Lock the candidate before evaluating silver. If nothing clears dev, use the remaining experimental budget on a compact, provenance-tracked training pack and a measured specialist LoRA smoke test only if time permits. Training is an alternative branch of the hour.

### 32–48 minutes · Evaluate one frozen challenger

- Check all changed dev labels and evaluate the frozen contrast pairs. Run the challenger on the **105-item silver holdout** only after it clears the dev and attribution checks. Use the exact baseline IDs and compare the full rows. Cluster resamples by item and by study where reliable study IDs link multiple records. Use 1,000 paired resamples with a fixed seed and report the full-set delta, interval, fraction of positive resamples, and number of changed items.
- Report results on the eligible PubMed slice, the full evaluation set, and the human-reviewed dev subset where available. Keep official composite as the headline. Also report aspect F1, sign and exact polarity, polarity QWK, quote overlap, and exact-citation validity. The official polarity and overlap metrics score only matched aspects, so include precision on **all** additions and counts of false emissions and recovered misses. Distinguish a correct label from a merely verbatim quote.
- Compare on the fresh audit if available. A reused silver holdout measures agreement with Gemini labels and is already part of earlier selection. A synthetic contrast pass tests specific behaviors. Keep these results separate.

### 48–60 minutes · Make and verify the release decision

A challenger needs all of the following before replacing the submission.

1. At least **60%** of dev additions match the gold aspect and exact polarity. Report the numerator and denominator. Require at least **five changed silver items** before using a high resample win rate as release evidence.
2. Dev composite stays within **0.02** of the shipped hybrid, with a positive silver composite delta and at least **80%** positive paired silver resamples. A dev drop that passes the numerical floor still requires examining where the errors moved.
3. Every accepted quote is verbatim and supports the rated drug and outcome. The frozen audit must show no recurring wrong-drug or unsupported-claim failure. In the absence of fresh real examples outside earlier selection, treat a pass as a **research candidate** pending that audit.
4. Any new adapter clears serving and export checks and is scored in the exact local runtime used for generation. Recheck transcript behavior only if changing the transcript route.

If the gate passes and the measured generation time plus validation fits the remaining time, run the exact frozen configuration offline on the 240 test inputs. Write a separate candidate file. Verify exact ID coverage, valid schema, verbatim citations, no unexpected field changes, and no inference failures. Preserve the previous file, then promote the validated candidate atomically and refresh the manifest. If the gate fails or time is short, retain the existing release and record the tested candidate and its status.

## When to refine the weights

Use the diagnostic to decide which examples would improve a specialist adapter. If the model picks the wrong sentence, teach target–outcome pairing and evidence IDs. If it picks a supported sentence and flips direction, train on balanced, guide-consistent positive, negative, and neutral outcomes. If it over-emits, include difficult unsupported examples such as aims, outcomes for another treatment, and mechanism-only claims. Preserve group separation for papers, study cohorts, and synthetic contrast families. Record whether each label came from a teacher, a provisional annotation, or an independent reviewer. Keep ambiguous or poorly aligned labels out of the specialist training targets until reviewed.

For a timed pilot, use the existing memory-bounded 4-bit MLX setup, assistant-token loss masking, and a separate checkpoint directory. Run a brief smoke test, monitor tokens per second and memory, and cap steps from measured throughput. Compare against the same base checkpoint with the same inputs and format. Evaluate abstention, direction, and evidence support before export. A lower training loss is a health check. If export and scoring will run past the hour, save the checkpoint and its recipe for the next session. The successful 120-step recipe and the Qwen normalization/convolution export correction are in the runbook. [Local model runbook](../../drug%20track/MAC_CHECK.md)

## Artifacts and updates

- Save a run manifest, baseline and candidate scores, change-level audit, frozen contrast cases, and one experiment log row per scored run. Keep generated outputs local under `out/`. Log the smallest useful next experiment even if no candidate passes.
- Post an update after baseline verification, after the diagnostic and first score, and when the release decision is known. During longer runs, report meaningful progress about once a minute.
- Stop at 60 minutes with the validated release or a clearly marked research candidate, the exact commands and artifact paths, and the remaining evidence gap.
