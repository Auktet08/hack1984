# HACK1984: Track 1 (Private Signals / Signal-to-Dose)

We are competing in the drug track: label public evidence on Tagrisso and Rybrevant/Lazcluze with signal type, actionable, and five aspects. It must run offline on a self-hosted model. **This folder (`hack1984/`) is the repo root.**

## Layout

- `drug track/`: the track. The organisers' files in it are **read-only and gitignored**: `README.md`, `LABELING_GUIDE.md`, `data/`, `scoring/`, `tools/` and `sample_submission.jsonl`. Don't edit, commit or post them. Use `data/*.full.jsonl`; these have the PubMed abstracts filled in.
  - `PROBLEM.md`: the plan and the decisions (model choice, teacher labels, startup, UI). `DATA.md`: data and scorer facts. `RESEARCH_README.md` + `research/ledger.jsonl`: Tavily/Exa usage rules and the log of searches already run.
  - `src/rules/predict.py --level N`: the current rules-only predictor. `src/eval/score_dev.sh` scores it on dev. `src/eval/log_exp.py` logs a result.
  - `analysis/`: data profiling and the early baselines.
- `docs/experiments/log.md`: **the only results table.** Every experiment from every session goes here.
- `docs/solutions/`: durable lessons (Compound Engineering learnings; write them with `/ce-compound`).
- `docs/ideation/`: idea evaluations and go/no-go.
- `CONCEPTS.md`: project vocabulary (aspect, matched aspect, composite, QWK cliff…). It's useful when a term in the guide, log or a lesson is ambiguous.

## Experiment protocol (always follow)

1. **Before** trying an idea, read `docs/experiments/log.md` (including "Decisions in force") and `docs/solutions/`. If it's already been tried, say so and don't rerun it unless something it depended on has changed.
2. Before any Tavily/Exa search, check `drug track/research/ledger.jsonl`, and log new searches there.
3. Run `"drug track/src/eval/score_dev.sh"`, or score.py with `--items data/dev.full.jsonl` for other predictors.
4. **After** every run, kept or not, append a row with `python3 "drug track/src/eval/log_exp.py" --score <score.json> --change "..." --verdict kept|reverted|superseded|info --note "..."`.
5. When a result teaches something non-obvious (a scorer quirk, a label-key habit, a trap), capture it with `/ce-compound` in `docs/solutions/`.
6. Never design rules from `test_inputs.jsonl`: read only dev, unlabeled and the guide. Test is for producing the submission only. Never send test items to a frontier model.
7. Dev is noisy (±0.055 at 95%): treat changes under ~0.02 as noise and say so.
