# Startup file contracts

These are the files the startup demo lanes pass to each other: labels, triage, the audit log, the gap view and
label cost. Each one has a JSON Schema (2020-12) here and a fixture in `fixtures/` cut from real ODAC transcript
rows. Build screens against the fixtures. When the real files exist under `out/startup/`, they have the same
shape, so no UI change is needed. (This is the startup-side counterpart of `../LABELS.md`.)

`out/` is gitignored, so a fresh checkout has only the fixtures. The app should fall back to them and say
**"fixture data"** on screen when it does.

| File (under `drug track/`) | Producer | Readers | Schema | Fixture |
|---|---|---|---|---|
| `out/startup/labels/<corpus>.jsonl` | `src/startup/label.py` (exists) | triage, gap view, app, S5 gate | `label_row.schema.json` | `fixtures/odac_labels.sample.jsonl` |
| `out/startup/triage/<corpus>.jsonl` | `src/startup/triage.py` (U2) | app | `triage_record.schema.json` | `fixtures/triage.sample.jsonl` |
| `out/startup/triage_audit.jsonl` | the app's decision endpoint only (U4), append-only | app | `triage_audit.schema.json` | `fixtures/triage_audit.sample.jsonl` |
| `out/startup/gap/<drug>.json` | `src/startup/gap_view.py` (U3) | app | `gap_view.schema.json` | `fixtures/gap_poziotinib.sample.json` |
| `out/startup/labels/<corpus>.<backend>.cost.json` | `label.py` (U11, U12) | app, deck | `label_cost.schema.json` | `fixtures/odac.gemini.cost.sample.json` |

## Check

```bash
python3 "drug track/contracts/validate.py"              # fixtures, plus real outputs when present
python3 "drug track/contracts/validate.py" --fixtures   # fixtures only
python3 -m unittest discover -s "drug track/tests" -t "drug track"
```

Besides the schemas, `validate.py` checks:

- every evidence `span` is the exact substring of its field at `start`;
- every quote span appears in its source row's text, when that row is loadable;
- `case_id` is `TRI-<turn_id>`, and `missing` lists exactly the unmet criteria;
- the gap view has one cell per aspect × column, at most one split and one thin flag per aspect, and every question points at a real flag;
- `usd_total` equals tokens × price.

## Rules every reader and writer follows

- **Never write "reportable"**, in a record or on screen. A record whose four criteria are all met is a
  **triage candidate** (`status: candidate`). Otherwise it is `incomplete`. It stays visible and names what's missing
  and why. The safety team decides what gets reported.
- **Stand-in badge.** `meta.stand_in` on label rows is the only stand-in signal. Every derived file carries
  `provenance.stand_in`, which is true if any input row was a stand-in. Show a "Gemini stand-in" badge wherever it's
  true. In triage records it refers only to the safety hint, because the four criteria are rules.
- **Label rows:** readers ignore unknown keys. Polarity is −2..+2. An aspect is null or `{span, polarity, speaker}`.
- **Triage:** one record per speaker turn. `item_ids` lists the turn's parts in order, and `texts` gives each
  part's text. Evidence `{item_id, field, span, start}` can come from any part. The UI shows `evidence[0]`: named
  side-effect terms come before generic ones ("side effects", "adverse event", "toxicity"), and ties go in turn order.
  Real output lists every match. The criteria follow ICH E2D(R1) §6.1: a group statement such as "82 percent of
  patients" never makes an identifiable patient.
- **Audit:** append-only. Builders never open it. Each line snapshots the record's `status`, `criteria` and `source`. For
  `confirmed_candidate`, `decided_at` (ISO 8601 with offset) is the awareness date.
- **Gap view:** `mean` is null when `n` is 0. A cell has at most 5 quotes, nearest the mean first. `side` is null on split
  flags, and `private`, `public` or `both` on thin flags. The thresholds are stored in the file so the screen can show them.
- **Cost:** stand-in runs always have `data_left_device: true`. Gemini runs record tokens and a dated price. Local runs
  record `wall_s` and `hardware`.

## Fixtures

They are cut from `out/startup/poziotinib_odac_turns.jsonl` and the Gemini stand-in labels, all from the public
FDA ODAC transcript (22 Sep 2022). There are no test or organiser items.

- `odac_labels.sample.jsonl`: `ODAC22-T147-1`, `T151-1..3`, `T054-6`, plus `T046-1`, `T048-2` and `T058`, which
  have no safety aspect.
- `triage.sample.jsonl`: `TRI-ODAC22-T151` (candidate, AE1), `TRI-ODAC22-T054` (incomplete, no identifiable
  patient, AE2) and `TRI-ODAC22-T147` (candidate, AE3).
- `triage_audit.sample.jsonl`: one `confirmed_candidate` (T151) and one `dismissed` (T054).
- `gap_poziotinib.sample.json`: computed from the real stand-in labels. It has AE4's four flags: split efficacy
  (FDA −1.20 vs public hearing +1.31), split safety (FDA −1.33 vs applicant +0.50), thin access/cost (both sides)
  and thin convenience (public side).
- `odac.gemini.cost.sample.json`: the ODAC stand-in run. 776,236 input and 26,409 output tokens at $0.75 / $3.75
  per 1M is $0.68 total, or $0.30 per 100 turns. Wall time wasn't recorded for that run.
