"""Build a small observed-outcome training set from audited training-pool excerpts."""
import argparse
import random
from collections import Counter
from pathlib import Path

from make_sentence_response_data import sentence_prompt
from predict_full import load_rows, write_atomic
import json

# Reviewed at the sentence level. These IDs belong to the exported training pool.
POSITIVE = set("""00605 00486 00745 00374 00889 00693 00475 00440 00625 00465 00740
00307 00871 00695 00375 00831 00303 00608 00381 00684 00844 00646""".split())
NEGATIVE = set("00051 00054 00040 00698 00791 00568 00653".split())
NEUTRAL = set("00794 00690 00600 00011 00331 00219".split())
# This quote describes an aim, mechanism, lab result, or later line's outcome.
UNSUPPORTED = set("00118 00869 00539 00532 00548 00053 00583 00204 00705 00438 00512 00595".split())


def example(key, product, evidence, code, provenance, context=""):
    return {"id": key, "provenance": provenance, "code": code,
            "messages": [{"role": "user", "content": sentence_prompt(product, evidence, context)},
                         {"role": "assistant", "content": code}]}


def new_pairs():
    examples = [
        ("neutral", "Median time to progression was indistinguishable between {drug} and standard therapy.", "C"),
        ("neutral", "The two arms had equivalent rates of clinical response, including the arm that received {drug}.", "C"),
        ("negative", "Imaging documented enlargement of the lung lesions after four months of {drug}.", "B"),
        ("negative", "The previously controlled tumor recurred while the patient continued {drug}.", "B"),
        ("negative", "At the first assessment after starting {drug}, imaging revealed new distant metastases.", "B"),
        ("unsupported", "The lesions enlarged during radiotherapy, before the patient ever received {drug}.", "D"),
        ("unsupported", "A response to docetaxel was documented. The team plans to start {drug} next.", "D"),
        ("unsupported", "Laboratory assays suggested a possible mechanism for reduced sensitivity to {drug}.", "D"),
        ("unsupported", "Previous studies suggested a benefit from {drug}, but this report evaluates a different drug and reports no outcome for the target.", "D"),
    ]
    for i, (kind, template, code) in enumerate(examples):
        for prod, drug in (("A", "osimertinib"), ("B", "amivantamab"), ("B", "lazertinib")):
            yield example(f"curated-synthetic-{i}-{drug}", prod, template.format(drug=drug), code,
                          f"synthetic {kind} contrast, separate from audit cases")
    comparisons = [
        ("The proportion of patients with tumor shrinkage was greater on osimertinib than on lazertinib.", "A", "B"),
        ("Patients receiving amivantamab had better disease control than those receiving osimertinib.", "B", "A"),
        ("Median overall survival did not differ between osimertinib and amivantamab in this cohort.", "C", "C"),
        ("The combination reduced progression compared with osimertinib alone; the combination contained lazertinib.", "B", "A"),
    ]
    for i, (sentence, polarity_a, polarity_b) in enumerate(comparisons):
        for prod, code in (("A", polarity_a), ("B", polarity_b)):
            yield example(f"curated-comparison-{i}-{prod}", prod, sentence, code, "synthetic comparator reversal")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    rows = load_rows(args.source / "train.jsonl")
    core = []
    spare_negatives = []
    for record in rows:
        key = record["id"]
        if key.startswith("synthetic-"):
            core.append(record)
            continue
        if key.endswith("-target-swap"):
            continue
        number = key.removeprefix("U-PM-")
        if number in UNSUPPORTED:
            record["code"] = "D"
            record["messages"][-1]["content"] = "D"
            record["provenance"] = "assistant-reviewed absence of observed target outcome in sentence"
            core.append(record)
        elif any(number in allow and record["code"] == code
                 for code, allow in (("A", POSITIVE), ("B", NEGATIVE), ("C", NEUTRAL))):
            record["provenance"] = "assistant-reviewed observed clinical outcome in training excerpt"
            core.append(record)
        elif record["code"] == "D":
            spare_negatives.append(record)
    rng = random.Random(1984)
    rng.shuffle(spare_negatives)
    examples = core + spare_negatives[:15] + list(new_pairs())
    rng.shuffle(examples)
    args.out.mkdir(parents=True, exist_ok=True)
    write_atomic(args.out / "train.jsonl", "".join(json.dumps(r) + "\n" for r in examples))
    write_atomic(args.out / "valid.jsonl", (args.source / "valid.jsonl").read_text())
    print(len(examples), dict(Counter(r["code"] for r in examples)))


if __name__ == "__main__":
    main()
