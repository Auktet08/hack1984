"""Probe two auditable outcome patterns on model-selected PubMed evidence."""
import argparse
import json
import re
from pathlib import Path

from gate_local import indexed
from predict_full import PRODUCT_MENTIONS, write_atomic

ENDPOINT = r"(?:median )?(?:overall survival|progression-free survival|(?:rw)?PFS|OS)"
EXCLUSIONS = re.compile(r"\b(?:not|never|may|might|could|whether|in vitro|mice|murine)\b", re.I)


def grounded_outcome(item, quote):
    target = PRODUCT_MENTIONS.get(item["product"])
    if not target or EXCLUSIONS.search(quote):
        return None
    patterns = (
        (rf"(?:{target})(?:-treated patients)? (?:showed|had|achieved) "
         rf"(?:significantly )?(?:improved|longer) {ENDPOINT}\b", 1),
        (rf"(?:{target})(?: groups?| arms?)?[, ]+(?:respectively, )?"
         rf"(?:the )?{ENDPOINT} (?:was|were) comparable\b", 0),
    )
    for pattern, polarity in patterns:
        match = re.search(pattern, quote, re.I)
        if match:
            return {"polarity": polarity, "span": match[0], "speaker": "researcher"}
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    items, baseline, candidate = map(indexed, (args.items, args.baseline, args.candidate))
    count = 0
    for key, item in items.items():
        if item["source"] != "pubmed" or baseline[key]["efficacy"] is not None:
            continue
        label = candidate[key]["efficacy"]
        if label and label["span"] in item["text"]:
            baseline[key]["efficacy"] = grounded_outcome(item, label["span"])
            count += baseline[key]["efficacy"] is not None
    write_atomic(args.output, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in baseline.values()))
    print(f"{count} grounded efficacy additions")


if __name__ == "__main__":
    main()
