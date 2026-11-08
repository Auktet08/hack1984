"""Check exact item coverage, valid labels and verbatim citations."""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from predict_full import ASP, SIGNALS, SPEAKERS, load_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("items")
    ap.add_argument("predictions")
    ap.add_argument("--count", type=int, default=240)
    args = ap.parse_args()
    items, predictions = load_rows(args.items), load_rows(args.predictions)
    source = {r["item_id"]: r["text"] for r in items}
    ids = Counter(r["item_id"] for r in predictions)
    if len(items) != args.count or len(source) != args.count or ids != Counter(source.keys()):
        ap.error(f"Expected one prediction per supplied ID and exactly {args.count} IDs")
    polarities = set()
    for row in predictions:
        key = row["item_id"]
        if (set(row) != {"item_id", "signal_type", "actionable", *ASP}
                or row["signal_type"] not in SIGNALS or row["actionable"] not in ("yes", "no")):
            ap.error(f"{key}: invalid prediction fields")
        for aspect in ASP:
            value = row[aspect]
            if value is None:
                continue
            if (not isinstance(value, dict) or set(value) != {"polarity", "speaker", "span"}
                    or type(value["polarity"]) is not int or not -2 <= value["polarity"] <= 2
                    or value["speaker"] not in SPEAKERS or not isinstance(value["span"], str)
                    or not value["span"].strip() or value["span"] not in source[key]):
                ap.error(f"{key}: invalid {aspect} label or citation")
            polarities.add(value["polarity"])
    if len(polarities) < 2:
        ap.error("Expected at least two distinct aspect polarities")
    print(f"Verified {len(ids)} predictions and all citations")


if __name__ == "__main__":
    main()
