# Experiment log: HACK1984 Track 1 (Private Signals)

**Read this before trying anything.** If a row already covers your idea, don't rerun it unless something it depended on has changed (and say what changed in the new row).

All scores are on **dev** (60 items) with `drug track/src/eval/score_dev.sh`, which runs `score.py --items data/dev.full.jsonl`. "Human" is the composite on the 15 human-reviewed items. The 95% bootstrap range on dev is about ±0.055, so differences under ~0.02 are noise. Rules marked *dev-fitted* were written after reading dev answers, so expect test to come in lower.

**Ground rule:** never design rules from `test_inputs.jsonl`. Rows marked *test-tainted* break this and must not be reused.

Add a row: `python3 "drug track/src/eval/log_exp.py" --score "drug track/out/dev/score_L3.json" --change "..." --verdict kept|reverted|superseded|info --note "..."`

This is the **only** results table. `PROBLEM.md` §5 mentions `EVAL.md`; that now means this file.

Verdicts:
- **kept:** in the current pipeline.
- **reverted:** tried, worse, removed.
- **superseded:** replaced by a later row.
- **info:** a measurement, not a change.

## Results

| ID | Date | Change | Composite | Human | Signal mF1 | Action F1 | Aspect F1 | QWK | Span F1 | Verdict | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E001 | 2026-11-07 | All "none" (sample-submission shape, dev ids) | 0.004 | 0.004 | 0.023 | 0.000 | 0.000 | — | — | info | Floor. |
| E002 | 2026-11-07 | Zero aspects, otherwise rules v1 signal/actionable | 0.167 | — | — | — | 0.000 | — | — | info | Never submit zero aspects: QWK, speaker and span count as 0. |
| E003 | 2026-11-07 | Exploratory rules v1 (ideation agent `base.py`) | 0.731 | 0.775 | 0.401 | 0.600 | 0.303 | 1.000 | 0.811 | superseded | Replaced by E005. |
| E004 | 2026-11-07 | Exploratory rules v2: title regexes + fda_event span tweak | 0.844 | — | 0.909 | — | — | 1.000 | — | superseded | **Test-tainted** (agent printed test inputs) and dev-fitted. Don't reuse its regexes. |
| E005 | 2026-11-07 | `src/rules/predict.py --level 1`: guide rules by source | 0.720 | 0.741 | 0.355 | 0.571 | 0.303 | 1.000 | 0.811 | kept | Base layer. QWK 1.0 is fragile (all matched = fda_event −1). |
| E006 | 2026-11-07 | Level 2: rare-class title keywords (earnings, guideline, access, approval, review, protocol, case report) | 0.819 | 0.871 | 0.856 | 0.762 | 0.303 | 1.000 | 0.811 | kept | Biggest single gain. Dev-fitted. |
| E007 | 2026-11-07 | Level 3: cue-word aspects on PubMed + press + news, cue-only spans | 0.827 | 0.837 | 0.856 | 0.762 | 0.651 | 0.861 | 0.656 | superseded | "retrospective" / "safety profile" cues misfire on press releases (they cite other studies). |
| E008 | 2026-11-07 | Level 3: safety + evidence cues PubMed-only, spans widened to the clause (≤16 words) | 0.828 | 0.867 | 0.856 | 0.762 | 0.617 | 0.933 | 0.629 | reverted | Clause widening lowered span F1 (0.731 → 0.629, compared with E009). The composite gap of 0.015 is within noise; span F1 is the real signal. Worth retrying only with a smarter trimmer, e.g. subject + verb + cue. |
| E009 | 2026-11-07 | Level 3: safety + evidence cues PubMed-only, cue-only spans | 0.843 | 0.864 | 0.856 | 0.762 | 0.617 | 0.933 | 0.731 | kept | Current best. QWK no longer all −1 (cliff hedged). Dev-fitted. |
| E010 | 2026-11-07 | Simulated: one fda_event gold polarity ≠ −1, against E004-style output | 0.701 | — | — | — | — | 0.000 | — | info | QWK cliff: −0.143 if every matched polarity is identical. Hedged with cue aspects: 0.860. |
| E011 | 2026-11-07 | Exploratory cue-word pass `lex2.py` (11 PubMed aspects) on top of E004 | 0.862 | — | — | — | 0.546 | 0.981 | 0.819 | info | Dev-fitted, built on the test-tainted E004. An upper bound only. |
| E012 | 2026-11-07 | B1 (`analysis/baseline.py`, other session): rules for ctgov/fda_event/fda_label only | 0.628 | — | 0.28 | 0.00 | 0.30 | 1.000 | 0.81 | info | From `drug track/DATA.md` §6. |
| E013 | 2026-11-07 | B1 with fda_event span = first 3 reactions | 0.630 | — | 0.28 | 0.00 | 0.30 | 1.000 | 0.82 | info | Span choice barely matters at this level. |
| E014 | 2026-11-07 | B2 = B1 + pubmed/news/PR → efficacy, PR → actionable yes | 0.710 | — | 0.33 | 0.53 | 0.30 | 1.000 | 0.81 | superseded | Equivalent to E005. |
| E015 | 2026-11-07 | O1 oracle: gold on ctgov/fda_event only | 0.648 | — | 0.23 | 0.00 | 0.30 | 1.000 | 1.00 | info | Perfect rules on those sources alone cap at ~0.65. |
| E016 | 2026-11-07 | O2 oracle: gold everywhere | 1.000 | — | 1 | 1 | 1 | 1 | 1 | info | Sanity check of the scorer. |
<!-- new rows above this line -->

## Ideas already considered and rejected (not run)

See `docs/ideation/2026-11-07-hack1984-private-signals-ideation.html` (Rejection Summary). In short:
- ~~Frontier-API silver labels + distillation~~: the ideation rejected it on privacy grounds, but **you have since ruled it allowed** for the unlabeled items (`PROBLEM.md` §4.3). Never send test items.
- Searching only the CONCLUSIONS section of abstracts: gold spans are spread across sections.
- ctgov actionable "yes" for new phase 3s: dev says 10/10 "no".
- Self-consistency voting: costs more and doesn't address the main risk.
- No-LLM weak supervision only.

## Decisions in force (details in `drug track/PROBLEM.md`)

- **Model:** treat the track description's 3B-parameter cap as binding (`README.md` itself sets no limit). Iterate on **Qwen3.5-2B**; keep a 9B profile on standby in case the cap is lifted (§4.2).
- **Teacher labels:** frontier-model labels on the 1,733 unlabeled items are allowed, for distillation (§4.3).
- **Research credits:** Tavily/Exa usage is logged in `drug track/research/ledger.jsonl`, per `RESEARCH_README.md`. Check that before searching again.

## Open leads

- 31 of 56 dev aspects are still missed, mostly PubMed efficacy claims without cue words. That's the case for a small local model.
- The real-world downgrade (+2 → +1) is right for PM-0022 and wrong for PM-0089. It needs a better signal than "real-world appears anywhere".
- Hand-label about 100 unlabeled items as an honest validation set (ideation idea 5).
