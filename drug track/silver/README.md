# Gemini silver labels

Teacher labels from Gemini on the unlabeled items, made with `src/teacher/gemini_label.py`. Use them for few-shot
examples, rare-class examples and checking the rules on test-like items. **Don't treat them as gold.**

## Files

| File | What it is |
|---|---|
| `unlabeled_gemini.checked.jsonl` | **Use this one.** 1,038 items (pubmed, news, press_release, fda_label) after the span check. Every span is an exact substring of the item text |
| `unlabeled_gemini.raw.jsonl` | The same replies before the span check, kept for comparison |
| `unlabeled_gemini.stats.json` | Tokens, failures and span-check counts for the run |
| `dev_gemini.checked.jsonl` / `dev_gemini.checked.score.json` | The same setup on the 60 dev items, with its score |

Format: the submission format (`item_id`, `signal_type`, `actionable`, five aspects), plus a `comment` with
Gemini's reason. Join to the item text on `item_id` in `data/unlabeled.full.jsonl`. fda_event and ctgov items
were left out, because the rules handle them.

## How they were made

- Model `gemini-3.8-flash` (direct API), thinking level low, temperature 0, JSON output enforced by the API's schema.
- Prompt: the full `LABELING_GUIDE.md` plus 3 dev examples from the same source.
- Span check: keep an exact match; otherwise repair case, quote and spacing differences, or a near-miss within one
  sentence; otherwise drop the aspect. On the unlabeled run: 1,064 ok, 14 repaired, 57 dropped. 54 of the dropped
  spans were quoted from the title, which the scorer doesn't accept.

## How good they are (dev, 60 items; log rows E021 and E022)

| | composite | aspect F1 | span F1 | human-reviewed composite (15 items) |
|---|---|---|---|---|
| Gemini + span check | 0.876 | 0.860 | 0.632 | 0.854 |
| Rules L3 | 0.843 | 0.617 | 0.731 | 0.864 |

Gemini matches far more aspects than the rules (49 vs 25 of 56), but quotes less precisely than gold. Most dev gold
was drafted by a frontier model, which may flatter Gemini. Dev noise is ±0.055.

**Never** run the labeler on `test_inputs`: the script refuses any file with "test" in its name.
