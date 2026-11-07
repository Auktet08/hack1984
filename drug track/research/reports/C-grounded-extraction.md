# Target C: grounded extraction tooling (research report)

Run: 2026-11-07, session `claude-C`. Plan: `research/plans/C-grounded-extraction.md`.
This is research only. Nothing was installed or added to the pipeline. Raw responses are in `research/raw/*C*`, and
the merged, deduplicated source list (127 URLs) is `research/raw/C-merged.json`.

**What this report is for.** It mostly **protects points** (citation validity, JSON validity) and feeds
`PROBLEM.md` §13.2. It does not settle §13.2. Every expected effect below is a hypothesis to test on dev, which is
noisy at ±0.055.

**Health warning on the Tavily Research mini reports** (`tavres-C-1/2.json`). Many of the numbers they give could not
be traced to their cited source and look invented. Examples: "LangExtract schema conformance > 95 %",
"span-aligner > 98 % recovery", "CopyGen +35 % exact match", "constrained beam search 71 → 88 %", "MINA recovers
> 99.95 % of gold rationales" (MINA is a coreference minimum-span paper, not a rationale extractor),
"clause-segmenter F1 ≈ 84 %" and "GLiNER F1 ≈ 56 %". None of these are used below. The verdicts rest only on READMEs
and papers read through Exa highlights or Tavily extract.

---

## 1. Top picks

Context from the repo: `PROBLEM.md` §4.4 already proposes `{aspect, polarity, sentence_no, cue}` with code doing the
quoting. The scorer's span F1 is bag-of-words: lowercased, split on whitespace, with **punctuation left attached**.
Gold spans have a median of 8 words, and none ends in punctuation (`DATA.md`). In E008, widening spans to the clause
dropped span F1 from 0.731 to 0.629.

### Pick 1: sentence pointer plus a short verbatim "cue anchor" that code locates (forms a + b)

- **What.** The model emits `sentence_no` plus a 2–6 word verbatim `cue`. Code then does three things:
  1. It finds the cue inside that sentence, trying in order: exact, then normalised (unicode quotes and dashes, NBSP,
     whitespace, case), then ordered-token subsequence, then LCS fuzzy.
  2. If the cue is not in that sentence, it searches neighbouring sentences and then the whole document. If the cue is
     still not found, it drops the aspect.
  3. It emits `source[start:end]` (never the model's own string) and passes it to the trimmer (pick 4).
- **Evidence.**
  - `gmhoward9289-ops/trust-but-anchor` (Apache-2.0, pushed 2026-08, README read). Even when told to quote verbatim,
    models produce a character-exact quote only 64–73 % of the time on adversarial documents. When code locates a
    3–8 word model-proposed anchor, coverage is 91–100 %, and every span is a real substring by construction. They
    measured 52 local models. Few-shot examples took one 8B model from 53 % to 90 % coverage.
  - The locate cascade is exact → normalised → ordered-token subsequence → fuzzy. Repeated phrases are disambiguated
    with a second anchor (`locate_pair`).
  - The "landmarks" write-up (felixlabelle.com, 2025) describes the same start/end-anchor idea and adds metrics worth
    logging: ambiguity rate and anchor failure rate.
- **Target metrics.** Citation validity stays at 1.0 by construction. Span F1 should hold or rise compared with
  free-text snapping. Output tokens drop, because a cue is about 4 words where a full quote is about 8 or more.
- **Expected effect on dev.** Small or neutral on composite. Its value is downside protection, since a paraphrased
  span scores 0. The token saving helps the cost-per-100-items criterion.
- **Effort.** About 2 h for the cascade, with tests on dev spans. Do not install `trust-but-anchor`; port the cascade,
  which is about 80 lines.
- **Risks.**
  - A 2B model may miscount sentence numbers on long press releases. Mitigate with inline `[S12]` markers, an integer
    enum of valid IDs in the JSON schema (pick 3), and the whole-document fallback.
  - A cue that repeats in the sentence is ambiguous. Choose the occurrence nearest the aspect keyword.
- **Experiment.** On dev, with the same model and prompt family, compare three arms: (A) a free-text span snapped by
  pick 2, (B) `sentence_no` + cue + trimmer, and (C) `sentence_no` only + trimmer. Log span F1, citation validity,
  the rate of not-located spans and output tokens per item.

### Pick 2: port LangExtract's alignment cascade as the snap fallback (form b)

- **What.** `google/langextract` (Apache-2.0, 39k stars, pushed 2026-11-07; `resolver.py` and `resolver-params.md`
  read; the Elixir port's `guides/alignment.md` documents the same semantics). The order is:
  1. **Occurrence DP.** Order-preserving and non-overlapping, so a repeated mention maps to the next occurrence.
  2. **Exact.** A contiguous run of lowercased word tokens.
  3. **"Lesser" prefix match.** The model over-extracted or stitched two quotes, so the span is grounded to the
     longest exact block anchored at its first token.
  4. **LCS fuzzy.** Longest common subsequence over lowercased, lightly stemmed tokens. It takes the tightest window
     with coverage ≥ 0.75 and density ≥ 1/3; LangExtract's cost note is O(n·m²).
  5. Otherwise `char_interval=None`, and the aspect is dropped.
- Map token indices back to character offsets and emit `source[s:e]`, which is case-exact.
- **Cheaper alternative.** `rapidfuzz.fuzz.partial_ratio_alignment` (MIT, pushed 2026-11) returns the best-matching
  source window and its offsets in one call. Use it as the fuzzy step if porting the LCS takes too long.
- **Trap.** Some ports use byte offsets. Python `str` slicing works on characters; keep it that way.
- **Target metrics.** Citation validity, by repairing paraphrased spans instead of dropping them. Span F1.
- **Expected effect on dev.** It only matters when the model writes free text: arm A in pick 1, or transcripts. It is
  neutral for rules output, whose spans are already exact.
- **Effort.** 1–1.5 h as a pure-Python port with no dependency.
- **Risk.** A fuzzy match can land on the wrong window. Keep the density threshold, restrict the search to the pointed
  sentence first, and log the share of spans that matched at each status.
- **Experiment.** Perturb the dev gold spans synthetically (case, punctuation, a dropped word, a paraphrased word) and
  measure the recovery rate and span F1 after snapping. This needs no model.

### Pick 3: constrained JSON with llama.cpp `json_schema` or XGrammar; keep the schema in the prompt and put evidence fields first (forms a + c)

- **Evidence.**
  - "Small LLM JSON output" (aitoollabs.dev, 2026-10, page read) tested **Qwen 3.5 2B Q4_K_M** on llama-server:
    - Without a grammar, 1 of 20 replies parsed as-is, because the model wraps output in a Markdown fence. After
      stripping the fence, 20 of 20 parsed and 20 of 20 were schema-valid.
    - Accuracy: all fields were right in 19 of 20 with the schema in the prompt, 18 of 20 with the grammar added, and
      only **13 of 20 with the grammar but no schema in the prompt**.
  - **The Constraint Tax** (arXiv 2605.26128, read). On sub-3B models, a hard answer-only schema raised validity from
    61.5 % to 100 % but cut accuracy from 19.7 % to 11.0 %. The tax was 20 points on Qwen2.5-1.5B and 15 points on
    Qwen2.5-3B. Their pattern: "reason free, constrain late".
  - **Structure Tax** (arXiv 2610.12056, AACL 2026). Putting reasoning or evidence fields before the answer matches
    free-form accuracy. Putting the answer field first causes steep drops, worst in small models.
  - arXiv 2609.23742 and StructureBench (IJCAI 2026) agree: constrained decoding gives 100 % validity, but semantic
    gains appear only on schema-aligned tasks.
- **What to do.**
  - Order the fields as `sentence_no → cue → aspect → polarity`, so evidence comes before judgement.
  - Make `sentence_no` an integer enum of the valid IDs.
  - Keep the schema text in the prompt.
  - Strip fences and `<think>` blocks in the parser in any case.
  - A/B the grammar on and off, because a grammar alone can cost accuracy on a 2B model.
- **Licences.** llama.cpp is MIT. XGrammar is Apache-2.0 (pushed 2026-11). lm-format-enforcer is MIT. Outlines is
  Apache-2.0.
- **Target metrics.** JSON validity reaches 1.0. It also protects aspect F1 and QWK from the schema tax.
- **Effort.** About 1 h, since the server option already exists.
- **Risk.** The grammar can hurt accuracy on a 2B model. Measure with and without it.
- **Experiment.** Run the same 2B prompt on dev under four conditions: {grammar, no grammar} × {evidence-first,
  label-first}. Log parse rate, aspect F1 and QWK.

### Pick 4: cue-anchored clause trimmer, the "smarter trimmer" lead from E008 (form b)

- **What.** A heuristic. The literature on minimal rationales mostly needs training (FRESH, Information Bottleneck,
  RE2, LimitedInk), so it does not fit by Sunday. The portable parts are:
  1. **Clause markers.** Split on `, ; : — (` and before subordinating conjunctions, wh-words and "that"
     (Dornescu et al. 2014, signs of syntactic complexity). Before splitting on a coordinating "and/or", require both
     sides to be at least about 3 words, so "safety and efficacy" stays whole (Trunq write-up).
  2. **Aspect subtree rule** (SZTE-NLP, SemEval-14). Grow from the cue until the span has at least 5 tokens, stopping
     at a clause boundary, and never take in another aspect's cue.
  3. **FRESH "contiguous" heuristic** (2005.00115). Choose the length-k window with the highest summed cue/keyword
     score, with k ≈ 8 from the dev median.
  4. **Strip trailing punctuation**, because the scorer keeps it attached to the token.
- **Evidence strength.** Weak to moderate. Published clause-boundary accuracy is 97 % where punctuation marks the
  boundary and 80 % overall (Siddharthan, cited in W17-6307). No tool targets 6–10 token evidence spans directly.
- **Target metric.** Span F1, currently 0.731.
- **Effort.** About 2 h.
- **Risk.** It overfits dev; with 56 spans, treat a gain under 0.02 as noise.
- **Experiment.** Plug it into `src/rules/predict.py --level 3` in place of the cue-only spans and compare with E009.
  It needs no model, so it is cheap.

### Pick 5 (supporting): pySBD `char_span=True` for sentence numbering with stable offsets (form c)

- **What.** MIT, 943 stars, last push 2024-08, which is stable but quiet. README read.
  `Segmenter(language="en", clean=False, char_span=True)` returns `TextSpan(sent, start, end)` over the original
  string.
- **Evidence.** The PySBD paper reports Golden Rules accuracy of 97.9 % against 52 % for the spaCy sentencizer, 75 %
  for blingfire and 56 % for NLTK, and 97.0 % on GENIA, which is biomedical.
- **Note.** `clean=True` cannot be combined with char spans. Navigation boilerplate in press releases needs separate
  handling, either filtering sentences before numbering or keeping the original offsets.
- **Target.** Stable `sentence_no` → offsets mapping for picks 1 and 4, including for 8k-character press releases.
- **Effort.** 0.5 h. **Only worth doing if** the current splitter in `predict.py` mis-splits on abbreviations,
  numbers like "p < 0.001" or bullets.

---

## 2. Pointer vs free-text spans (§13.2): what the evidence says

This section is input to the decision, not the decision itself.

- **Free-text quotes drift, even from strong models.** Told to quote verbatim, models produce an exact quote 64–73 %
  of the time (trust-but-anchor). LangExtract had to build an exact → lesser → LCS-fuzzy cascade because extraction
  text routinely differs from the source.
- **Pointing is safer, but whole-sentence pointers over-cover.** In SafeLLM (arXiv 2606.12897), selecting line
  numbers beat verbatim copying on recall (word recall 0.94 vs COPY), with zero hallucinated text. Precision was
  lower, and the "small" model there was qwen3:32b, not a model of 3B or fewer. A whole sentence is too long for our
  ~8-word gold spans: E008 showed widening hurts.
- **The best-supported form is a hybrid.** The model points to a sentence and gives a short verbatim cue, and code
  locates the cue and trims (picks 1 and 4). Free-text snapping (pick 2) remains as the fallback. This also cuts
  output tokens, which is plausible from the anchor write-ups, but no measured figure for a 2B model was found.
- **Gap.** No source measured whether a model of 3B or fewer counts sentence IDs reliably in documents of 8k or more
  characters. Arm C vs arm B in pick 1 answers that on our own data.

---

## 3. Full candidate table

The forms are (a) prompt or method, (b) portable algorithm, (c) library, (d) model.

| Candidate | URL | Form | Licence / activity | Verdict | Reason |
|---|---|---|---|---|---|
| Anchor locate cascade (trust-but-anchor) | github.com/gmhoward9289-ops/trust-but-anchor | a+b | Apache-2.0, 2026-08, 0★ | **adopt (port)** | README read; 64–73 % verbatim vs 91–100 % anchor coverage across 52 local models; substring by construction |
| LangExtract resolver cascade | github.com/google/langextract | b (c) | Apache-2.0, 2026-11, 39k★ | **adopt (port resolver logic)** | `resolver.py` and params read; exact/lesser/LCS + occurrence DP; the full library (chunking, multi-pass, Gemini/Ollama) is more than we need |
| llama.cpp `json_schema` / GBNF | github.com/ggml-org/llama.cpp | c | MIT, 2026-11 | **adopt with A/B** | Qwen3.5-2B test read: validity fixed, accuracy unchanged; keep schema in prompt; open issues with large `maxLength` and nesting, so keep the schema flat |
| Evidence-first field order (Structure Tax) | arxiv.org/abs/2610.12056 | a | paper (AACL 2026) | **adopt** | costs nothing to test; answer-first hurts small models |
| "Reason free, constrain late" (Constraint Tax) | arxiv.org/html/2605.26128 | a | paper | **adopt as guidance** | Qwen2.5 1.5B/3B lose 15–20 points under a hard answer-only schema |
| Cue-anchored clause trimmer (heuristics) | W14-5601, S14-2107, FRESH 2005.00115, Trunq | b | papers / blog | **adopt (build)** | no off-the-shelf tool; the heuristics port easily |
| pySBD char spans | github.com/nipunsadvilkar/pySBD | c | MIT, 2024-08, 943★ | maybe | strong Golden Rules and GENIA accuracy; only if our splitter fails |
| rapidfuzz `partial_ratio_alignment` | github.com/rapidfuzz/RapidFuzz | c | MIT, 2026-11, 4.2k★ | maybe | one-call fuzzy window and offsets; fallback for pick 2 |
| XGrammar | github.com/mlc-ai/xgrammar | c | Apache-2.0, 2026-11 | maybe | only if serving through vLLM/SGLang; 2609.23742 shows Qwen-0.6B content accuracy 0.871 → 0.943 |
| lm-format-enforcer | github.com/noamgat/lm-format-enforcer | c | MIT, 2026-04 | maybe | transformers path; no latency data found |
| Outlines | github.com/dottxt-ai/outlines | c | Apache-2.0, 2026-09 | maybe | equivalent; compile cost per schema |
| anchorite `locate_quote_span` (Smith-Waterman) | github.com/populationgenomics/anchorite | c/b | MIT, 2026-10, 3★ | maybe | SW-based quote → span; an alternative fuzzy step, little use |
| GLiNER2.5 (small 74M / base 194M) | github.com/fastino-ai/GLiNER2 | d | Apache-2.0, 2026-10/11 | maybe (post-deadline) | long-document chunking with global offsets (tutorial read: 384-word chunks, 64-word overlap, `text[start:end]==text` asserted); span attributes such as sentiment; no evidence it finds "claim" spans that match our gold |
| GLiNER-BioMed | github.com/ds4dh/GLiNER-biomed, HF Ihor/gliner-biomed-large-v1.0 | d | MIT code / Apache-2.0 weights | reject for now | biomedical entity NER (micro F1 59.8 zero-shot), not evidence clauses |
| deepset tinyroberta-squad2 (82M) / deberta-v3-base-squad2 (184M) | huggingface.co/deepset | d | **CC BY 4.0** (attribution) | maybe-low | extractive QA returns char offsets; SQuAD answers are short entities, so likely too short for 8-word evidence spans; untested |
| extractx (grounded-classification pattern) | github.com/veyorokon/extractx | a | **no licence**, 0★ | pattern only | "deterministic candidates, LLM picks IDs" is the same idea as pick 1; don't vendor |
| jevextract | github.com/gabazureus/jevextract | c | MIT, 2026-09, 2★ | reject | offsets by construction, but its own plot shows lower F1 than LLM methods; README is mostly images |
| SourceryForge | github.com/jolovicdev/sourcery | c | MIT, 2026-07, 4★ | reject | LangExtract-like framework, too heavy to adopt by Sunday |
| LangExtract ports (Rust/TS/Elixir) | modularflow, Divinci-AI, mdepolli | — | various | reference only | Elixir `guides/alignment.md` is the clearest spec of the cascade |
| quotellm (copy-constrained generation) | github.com/mwestera/quotellm | c | **no licence**, 2024 | reject | tested only on a 70B model; unlicensed |
| CopyGen (copy-constrained decoding) | neurips.cc poster 153537 | b | unverified | reject | claims came only from the mini report; no code verified |
| Trie / finite-set constrained decoding (STATIC, SachinKalsi, 2608.12574) | github.com/youtube/static-constraint-decoding etc. | b/c | various | reject | built for label sets or generative retrieval; an integer enum in the JSON schema covers our pointer case |
| SAM-Decoding (suffix automaton) | github.com/hyx1999/sam-decoding | c | — | reject | speeds up copying but does not constrain output; integration time too high |
| Ctrl-G, NCO-Decoding, seq2seq_constrained_decoding | github | c | — | reject | heavy (HMM/DFA) or the wrong constraint type |
| span-aligner (PyPI), Smith-Waterman (slavianap) | pypi / github | c | unverified / **no licence** | reject | only the mini report vouched for them; nothing checked |
| HF constrained beam search | huggingface.co/transformers-community | c | — | reject | forces words to appear, which is not the same as restricting output to substrings; beam search is slow |
| Clause-segmenter (PyPI) | pypi.org/project/clause-segmenter | c | unverified | reject | its metrics came only from the mini report |
| SafeLLM LINES strategy | arxiv.org/html/2606.12897v1 | a | paper | evidence for §13.2 | read; models of 32B and up only |
| Attribute or Abstain (LAB) | doi 10.18653/v1/2024.emnlp-main.463 | a | paper | context | small prompted models do better post-hoc; cite-in-one-step works best for large models |

---

## 4. Themes that came back thin

- **C4, copy-constrained / pointer decoding for models of 3B or fewer.** No maintained, licensed implementation was
  found that restricts generation to source substrings with a small model. There is also **no measured comparison of
  pointer vs quote on a model of 3B or fewer**: SafeLLM used 32B and up, and trust-but-anchor measured many local
  models, but its per-model table is off-site and not fetched. Our own A/B is the only way to settle it.
- **C5, trimming to 6–10 token evidence.** The rationale literature needs training. No tool is ready to use, so pick 4
  rests on heuristics.
- **C6 for our span type.** GLiNER handles entity-like spans and long documents well, but nothing shows it finds
  "claim or outcome" clauses.
- Following the plan, no Tavily Research pro run was used to fill gaps. Exa covered them instead (12 searches in
  total, under the cap of 15).

## 5. Spend

| Tool | Calls | Cost | Bucket | Cap |
|---|---|---|---|---|
| Tavily Research mini | 2 | not reported under OAuth (range 4–110 each, so 8–220) | C | 2 runs ✔ |
| Tavily search (basic, github.com + huggingface.co) | 5 | 5 credits | D | 5 ✔ |
| Tavily extract (basic) | 10 URLs (9 ok, 1 failed and free) | 2 credits | D | ≤ 10 credits ✔ |
| Exa MCP search | 12 | about $0.084 (estimate) | ad-hoc | ≤ 15 ✔ |
| Exa MCP fetch | 0 | $0 | ad-hoc | ≤ 10 ✔ |
| GitHub and HF REST | 22 | free | none | — |

## 6. Verification

- **Ledger.** There are 5 `"who":"claude-C"` lines: research ×2, search ×5, Exa ×12, GH/HF ×22, extract ×10. Every
  `out` file exists.
- **R1.** All 19 saved queries (`C-queries-tavres.txt`, `tav-C-1.json`, `exa-C-*.json`) were checked against the
  titles and IDs of the 480 test records. There were **0 matches**. Only the match count was printed.
- **Adopt verdicts.** Every adopt verdict has a stated licence and a README or paper read (`tavext-C-1/2.json`, or the
  README text in Exa highlights saved in `exa-C-*.json`).
