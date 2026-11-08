"""Create an evidence-aligned, training-pool-only clinical response dataset."""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from clinical_response import CLINICAL_CUES, indexed, make_prompt, shortlist
from predict_full import write_atomic

HARD_NEGATIVE = re.compile(
    r"\b(?:aim(?:ed|s)? to|objective was to|protocol|case of|adverse events?|"
    r"side effects?|toxicity|preclinical|in vitro|cell lines?)\b", re.I
)
NONCLINICAL = re.compile(r"\b(?:cell lines?|mice|murine|in vitro|xenografts?|docking)\b", re.I)
DIRECTION = {-1: "UNFAVORABLE", 0: "NEUTRAL", 1: "FAVORABLE"}


def example(row, gold):
    units = shortlist(row, broad=True)
    if not units:
        return None
    if gold:
        # The reference quote must align to a whole candidate sentence.
        support = next((u for u in units if gold["span"] and gold["span"] in u[2]), None)
        if not support or NONCLINICAL.search(support[2]) or not CLINICAL_CUES.search(support[2]):
            return None
        polarity = gold["polarity"]
        verdict = DIRECTION[(polarity > 0) - (polarity < 0)]
        target = {"verdict": verdict, "unit": support[1],
                  "strength": "strong" if abs(polarity) == 2 else "ordinary"}
        provenance = "teacher label with exact span alignment"
    elif any(HARD_NEGATIVE.search(u[2]) for u in units):
        verdict = "UNSUPPORTED"
        target = {"verdict": verdict, "unit": -1, "strength": "ordinary"}
        provenance = "teacher blank with a hard-negative cue"
    else:
        return None
    return {"id": row["item_id"], "provenance": provenance, "verdict": verdict,
            "messages": [{"role": "user", "content": make_prompt(row, units, True)},
                         {"role": "assistant", "content": json.dumps(target)}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    rows = indexed("out/silver/pool.full.jsonl")
    gold = indexed("out/silver/pool.gold.jsonl")
    holdout = indexed("out/silver/holdout.full.jsonl")
    dev = indexed("data/dev.full.jsonl")
    if rows.keys() & (holdout.keys() | dev.keys()):
        raise ValueError("Training pool overlaps the evaluation IDs")
    reserved = {r["text_sha256"] for r in (*dev.values(), *holdout.values())}
    groups = defaultdict(list)
    seen = set()
    for key, row in rows.items():
        if row["source"] != "pubmed" or row["text_sha256"] in reserved:
            continue
        title = re.sub(r"\W+", "", row["title"].casefold())
        if title in seen:
            continue
        item = example(row, gold[key]["efficacy"])
        if item is None:
            continue
        length = len(tokenizer.apply_chat_template(item["messages"], return_dict=False))
        if length > 1152:
            continue
        seen.add(title)
        groups[item["verdict"]].append(item)
    rng = random.Random(1984)
    train, valid = [], []
    for verdict, group in sorted(groups.items()):
        rng.shuffle(group)
        validation = min(12, max(1, len(group) // 8))
        valid.extend(group[:validation])
        train.extend(group[validation:validation + 75])
    rng.shuffle(train)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, records in (("train", train), ("valid", valid)):
        write_atomic(args.out / f"{name}.jsonl", "".join(json.dumps(r) + "\n" for r in records))
        print(name, len(records), dict(Counter(r["verdict"] for r in records)), flush=True)


if __name__ == "__main__":
    main()
