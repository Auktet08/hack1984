"""Derive sentence-level verdict training from a frozen specialist dataset."""
import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from rank_response import TASK
from clinical_response import target_pattern
from predict_full import PRODUCT_NAMES, load_rows, write_atomic

CODE = {"FAVORABLE": "A", "UNFAVORABLE": "B", "NEUTRAL": "C", "UNSUPPORTED": "D"}
TARGETS = {v: k for k, v in PRODUCT_NAMES.items()}
UNIT = re.compile(r"^Unit (\d+): ")


def sentence_prompt(product, sentence, previous):
    return f"{TASK}\nTarget: {PRODUCT_NAMES[product]}\nPreceding context: {previous}\nEvidence: {sentence}\nAnswer:"


def samples(row, augment):
    messages = row["messages"]
    target = json.loads(messages[-1]["content"])
    units = []
    for line in messages[0]["content"].splitlines():
        if line.startswith("Target: "):
            product = TARGETS[line.removeprefix("Target: ")]
        match = UNIT.match(line)
        if not match:
            continue
        data = line[match.end():]
        sentence, end = json.JSONDecoder().raw_decode(data)
        suffix = data[end:].removeprefix(" | preceding context: ")
        units.append((int(match[1]), sentence, json.loads(suffix) if suffix else ""))
    verdict = target["verdict"]
    if verdict == "UNSUPPORTED":
        _, sentence, previous = units[0]
    else:
        _, sentence, previous = next(u for u in units if u[0] == target["unit"])

    def sample(key, product, code, provenance):
        return {"id": key, "provenance": provenance, "code": code,
                "messages": [{"role": "user", "content": sentence_prompt(product, sentence, previous)},
                             {"role": "assistant", "content": code}]}

    yield sample(row["id"], product, CODE[verdict], row["provenance"])
    if augment and verdict != "UNSUPPORTED" and product in ("A", "B"):
        alternate = "B" if product == "A" else "A"
        if not re.search(target_pattern({"product": alternate}), previous + " " + sentence, re.I):
            yield sample(row["id"] + "-target-swap", alternate, "D", "same evidence, absent alternative drug")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for split in ("train", "valid"):
        records = [example for row in load_rows(args.source / f"{split}.jsonl")
                   for example in samples(row, augment=split == "train")]
        rng = random.Random(1984)
        rng.shuffle(records)
        if split == "train":
            swaps = [r for r in records if r["id"].endswith("-target-swap")]
            retained = {r["id"] for r in swaps[:30]}
            records = [r for r in records if not r["id"].endswith("-target-swap") or r["id"] in retained]
        write_atomic(args.out / f"{split}.jsonl", "".join(json.dumps(r) + "\n" for r in records))
        print(split, len(records), dict(Counter(r["code"] for r in records)))


if __name__ == "__main__":
    main()
