# Label files: how the UI reads them

The pipeline writes one label file per data split. The UI, the aggregator (trends and cards) and `/analyze` read
these files and nothing else from the pipeline. **The format is fixed.** The contents improve over time (rules
now, the local model later), but field names and types don't change, so nothing in the UI should need rework
when the labels are replaced.

## Get the files

`out/` is gitignored, so generate the files yourself. It takes under a second and needs no model, GPU or network.

```bash
cd "drug track"
python3 src/inference/export_labels.py                    # all splits
python3 src/inference/export_labels.py --splits unlabeled # just one
```

**Prerequisite:** `data/*.full.jsonl` must exist. They're the organisers' files (gitignored). If you only have
`data/*.jsonl`, run `python3 tools/rehydrate.py` once (this one needs the network, to fetch PubMed abstracts).

Rerun the script whenever you pull pipeline changes. It replaces each file in one step, so a running app never
reads a half-written file.

| File | Items | Notes |
|---|---:|---|
| `out/labels/dev.jsonl` | 60 | predicted labels (not the gold answers) |
| `out/labels/unlabeled.jsonl` | 1,733 | the bulk of the trend data |
| `out/labels/test.jsonl` | 240 | same labels as the submission |

For trends and the feed, load all three and treat them as one corpus of 2,033 items.

## One line = one item

```json
{
  "item_id": "PM-0004",
  "source": "pubmed",
  "url": "https://pubmed.ncbi.nlm.nih.gov/...",
  "published": "2025-01-09",
  "product": "A",
  "title": "...",
  "text": "... full item text ...",
  "signal_type": "efficacy",
  "actionable": "no",
  "efficacy": null,
  "safety": null,
  "convenience": null,
  "access_cost": null,
  "evidence_quality": {"polarity": -1, "speaker": "researcher", "span": "a retrospective cohort study"},
  "meta": {"by": "rules-L3", "confidence": 0.5}
}
```

| Field | Type / values |
|---|---|
| `item_id` | string, unique across all three files |
| `source` | `pubmed` · `ctgov` · `fda_event` · `fda_label` · `fda_notice` · `news` · `press_release` |
| `url` | link to the original |
| `published` | `YYYY-MM-DD`, always present (2025-01-01 to 2026-10-28) |
| `product` | `A` = Tagrisso (osimertinib) · `B` = Rybrevant/Lazcluze (amivantamab/lazertinib) · `both` |
| `title`, `text` | the item as we read it. News items are headline + snippet only |
| `signal_type` | `efficacy` · `safety` · `regulatory` · `trial_update` · `competitor_move` · `access_pricing` · `guideline` · `expert_opinion` · `none` |
| `actionable` | `"yes"` / `"no"` (strings, not booleans) |
| five aspect keys | always present. `null` = the item doesn't judge the product on that aspect |
| aspect `.polarity` | integer −2 … +2 (−2 strongly negative, 0 neutral/mixed, +2 strongly positive), about **our** product |
| aspect `.speaker` | `researcher` · `hcp` · `patient` · `payer` · `regulator` · `company` · `media` |
| aspect `.span` | the quote that justifies the label |
| `meta.by` | what produced the label: `rules-L3` today, a model profile such as `qwen35-2b` later |
| `meta.confidence` | 0–1. **Placeholder for now** (0.9 for ctgov/fda_event/fda_notice, 0.7 fda_label, 0.5 others) |

**Guarantees you can rely on:**
- Every `span` is an exact substring of `text`. To highlight it: `start = text.indexOf(span)`,
  `end = start + span.length`. Show the "verbatim ✓" badge on that basis.
- All five aspect keys are present on every line, and every non-null aspect has all three fields.

**Code defensively against:** extra keys appearing later (ignore unknown fields), an aspect or signal value that
never shows up in today's data, and items with no aspects at all (most of them).

## What today's data looks like (rules-L3)

Build for the full schema, but expect the first-iteration data to be thin and lopsided:
- **759 of 2,033 items have at least one aspect.** Most aspects are `safety −1` from FDA adverse-event reports
  (speaker `hcp` or `patient`).
- **`convenience` and `access_cost` are always null**, and `evidence_quality` is always −1. Those trend lines
  will be empty or flat until the model lands. Use the empty state, not hidden charts.
- Efficacy: 98 aspects, mostly +2 or −1.
- 101 items are actionable: efficacy 46, regulatory 37, guideline 11, access_pricing 6, safety 1.
- 96 ISO weeks with data, 9–32 items per week (median 21).

## What you build on top (PROBLEM.md §9)

- **`out/trends.json`** (aggregator): weekly buckets on `published`; mean polarity and n per
  (product, aspect, speaker); quotes = the spans behind each point; shifts where |Δ| ≥ 0.5 with n ≥ 3, or the
  sign flips.
  `{series: [{product, aspect, speaker, week, mean, n, quotes: [{item_id, span, polarity}]}], shifts: [{product, aspect, speaker, week, delta}]}`
- **`out/cards.json`** (card writer): actionable items → cards.
  `[{card_id, published, product, signal_type, actionable, headline, why, confidence, citations: [{item_id, url, span}]}]`
- **`POST /analyze {text, title?, source?}`** → `{labels, card, latency_ms}`. Until the model path exists, it
  can call `predict(item, 3)` from `src/rules/predict.py`. Note that rules return almost nothing for transcripts.

Make the aggregator a script that rebuilds from the label files, because they will be regenerated (when rules
improve, when the model beats rules, and the final relabel on Sunday morning).

**Don't hand-edit label files.** The next regeneration overwrites them. Report wrong labels to the pipeline
owner instead.
