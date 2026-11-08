"""Compare polarity from selected and gold spans with the same local model."""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "inference"))
from predict_full import ASP, LOCAL_HTTP, PRODUCT_NAMES, load_rows

URL = "http://127.0.0.1:18083/v1/chat/completions"


def classify(case, url, model):
    row, aspect, span = case
    product = PRODUCT_NAMES.get(row["product"], row["product"])
    prompt = (
        f"Rate {aspect} for {product} using the quoted evidence. "
        "Use -2 for strongly unfavorable, -1 for mildly unfavorable, 0 for neutral or mixed, "
        "1 for mildly favorable, and 2 for strongly favorable. Use null if the quote does "
        "not establish a judgment. A rival outperforming the target is unfavorable. "
        "No new safety signals is neutral. Study limitations lower evidence quality. "
        f"Return JSON with one key polarity. Evidence: {json.dumps(span)}"
    )
    payload = {
        "model": model, "temperature": 0, "max_tokens": 48,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "rating", "schema": {"type": "object", "properties": {
                "polarity": {"enum": [-2, -1, 0, 1, 2, None]}},
                "required": ["polarity"], "additionalProperties": False}}},
    }
    req = Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with LOCAL_HTTP.open(req, timeout=90) as reply:
        answer = json.load(reply)["choices"][0]["message"]["content"]
    return json.loads(answer)["polarity"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items")
    parser.add_argument("predictions")
    parser.add_argument("rules")
    parser.add_argument("out", type=Path)
    parser.add_argument("--url", default=URL)
    parser.add_argument("--model", default="qwen35-2b-lora-v1")
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("Expected a loopback model endpoint")
    preds, rules = ({r["item_id"]: r for r in load_rows(p)} for p in (args.predictions, args.rules))
    cases = []
    for row in load_rows(args.items):
        key = row["item_id"]
        for aspect in ASP:
            gold, pred = row[aspect], preds[key][aspect]
            if gold and pred and rules[key][aspect] is None:
                cases.append((row, aspect, gold, pred))
    jobs = [(row, aspect, label["span"]) for row, aspect, gold, pred in cases for label in (gold, pred)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda job: classify(job, args.url, args.model), jobs))
    report = []
    for (row, aspect, gold, pred), gold_rating, pred_rating in zip(cases, results[::2], results[1::2]):
        report.append({"item_id": row["item_id"], "aspect": aspect, "gold": gold, "selected": pred,
                       "with_gold_quote": gold_rating, "with_selected_quote": pred_rating})
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{len(report)} matched model-added aspects")
    for field in ("original", "with_gold_quote", "with_selected_quote"):
        correct = sum((r["selected"]["polarity"] if field == "original" else r[field]) ==
                      r["gold"]["polarity"] for r in report)
        print(f"{field}: {correct}/{len(report)} exact")


if __name__ == "__main__":
    main()
