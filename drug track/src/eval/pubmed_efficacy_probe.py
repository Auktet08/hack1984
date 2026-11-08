"""Evaluate a conservative, evidence-gated PubMed efficacy addition."""
import argparse
import json
import re
from pathlib import Path

from gate_local import indexed
from predict_full import PRODUCT_MENTIONS

OUTCOME = re.compile(
    r"(?P<strong>significantly )?(?:improved|prolonged) "
    r"(?:progression-free survival|overall survival|PFS|OS)\b",
    re.I,
)
UNCERTAIN = re.compile(r"\b(?:not|never|may|might|could|whether)\b", re.I)


def addition(item, proposed):
    if item["source"] != "pubmed" or proposed is None:
        return None
    span = proposed["span"]
    target = PRODUCT_MENTIONS.get(item["product"])
    if not target or span not in item["text"]:
        return None
    # Require the target to be the grammatical subject immediately before the outcome.
    claim = re.fullmatch(rf"(?:{target})\s+(?:{OUTCOME.pattern})", span, re.I)
    if claim and not UNCERTAIN.search(span):
        return {**proposed, "polarity": 2 if claim["strong"] else 1}
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items")
    parser.add_argument("baseline")
    parser.add_argument("model")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    items, baseline, model = map(indexed, (args.items, args.baseline, args.model))
    count = 0
    for key, row in baseline.items():
        if row["efficacy"] is None:
            row["efficacy"] = addition(items[key], model[key]["efficacy"])
            count += row["efficacy"] is not None
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in baseline.values()),
                           encoding="utf-8")
    print(f"Added {count} PubMed efficacy labels")


if __name__ == "__main__":
    main()
