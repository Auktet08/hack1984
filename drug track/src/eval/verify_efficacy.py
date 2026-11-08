"""Measure whether a local support verifier can reject unsupported efficacy quotes."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request

from gate_local import indexed
from predict_full import LOCAL_HTTP, PRODUCT_NAMES, write_atomic

URL = "http://127.0.0.1:18080/v1/chat/completions"


def verify(case):
    item, label = case
    target = PRODUCT_NAMES.get(item["product"], item["product"])
    quote = label["span"]
    prompt = (
        f"Target treatment: {target}. Decide whether this quote explicitly reports a clinical "
        "efficacy outcome attributable to the target. A trial objective, molecular finding, "
        "background, toxicity, or result for another treatment is insufficient. "
        "If the quote does not identify the treatment or clearly connect it to the outcome, "
        "answer unsupported. A rival comparison qualifies only if the target is explicitly "
        "one of the compared groups. Return JSON with the key verdict and value supported or unsupported. "
        f"Quote: {json.dumps(quote)}"
    )
    body = {
        "model": "qwen3.5-2b", "temperature": 0, "max_tokens": 48,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "support", "schema": {
            "type": "object", "properties": {"verdict": {"enum": ["unsupported", "supported"]}},
            "required": ["verdict"], "additionalProperties": False}}},
    }
    req = Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with LOCAL_HTTP.open(req, timeout=90) as reply:
        content = json.load(reply)["choices"][0]["message"]["content"]
    return json.loads(content)["verdict"] == "supported"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("items", "baseline", "candidate"):
        parser.add_argument(name)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    items, baseline, candidate = map(indexed, (args.items, args.baseline, args.candidate))
    cases = [(item, candidate[key]["efficacy"]) for key, item in items.items()
             if item["source"] == "pubmed" and baseline[key]["efficacy"] is None
             and candidate[key]["efficacy"]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        verdicts = list(pool.map(verify, cases))
    for (item, label), supported in zip(cases, verdicts):
        if supported:
            baseline[item["item_id"]]["efficacy"] = label
    write_atomic(args.output, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in baseline.values()))
    print(f"Accepted {sum(verdicts)}/{len(cases)} efficacy proposals")


if __name__ == "__main__":
    main()
