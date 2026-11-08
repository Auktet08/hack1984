"""Filter the specialist training data and add controlled attribution examples."""
import argparse
import json
import re
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from clinical_response import indexed, make_prompt, shortlist, target_pattern
from predict_full import load_rows, write_atomic

SUPPORT = {
    "FAVORABLE": re.compile(r"\b(?:benefit|improv\w*|prolong\w*|respond\w*|response|regress\w*|remission|control|effectiv\w*|superior|longer)\b", re.I),
    "UNFAVORABLE": re.compile(r"\b(?:progress\w*|fail\w*|resistan\w*|poorer|worse|shorter|inferior|did not meet)\b", re.I),
    "NEUTRAL": re.compile(r"\b(?:comparable|similar|equivalent|noninferior|stable|no significant difference)\b", re.I),
}
BACKGROUND = re.compile(r"\b(?:aim(?:s|ed)? to|designed to|hypothes\w*|expected to|in vitro|xenograft\w*|cell lines?|mouse|mice)\b", re.I)
TRIAL = re.compile(r"\bNCT\d{8}\b", re.I)


def trial_ids(row):
    return {match.upper() for match in TRIAL.findall(row["text"])}


def verified(row, record):
    target = json.loads(record["messages"][-1]["content"])
    units = shortlist(row, broad=True)
    verdict = target["verdict"]
    if verdict == "UNSUPPORTED":
        return not any(named and not BACKGROUND.search(sentence) and
                       any(pattern.search(sentence) for pattern in SUPPORT.values())
                       for named, _, sentence, _ in units)
    evidence = next((sentence for _, unit, sentence, _ in units if unit == target["unit"]), "")
    # Keep only explicit target and direction pairs in the selected source sentence.
    return bool(re.search(target_pattern(row), evidence, re.I) and not BACKGROUND.search(evidence)
                and SUPPORT[verdict].search(evidence))


def contrasts():
    family = [
        ("benefit", "Radiographic assessment found that tumor burden decreased during {drug} therapy.", "FAVORABLE"),
        ("benefit", "After the switch to {drug}, follow-up imaging showed sustained reduction in tumor volume.", "FAVORABLE"),
        ("unfavorable", "The patient developed new metastatic lesions while receiving {drug}. Disease progression was documented.", "UNFAVORABLE"),
        ("unfavorable", "The scan confirmed enlargement of the measurable lesions despite ongoing {drug} therapy.", "UNFAVORABLE"),
        ("neutral", "Median survival was similar in the {drug} and control groups.", "NEUTRAL"),
        ("neutral", "Tumor size was unchanged during follow-up on {drug}.", "NEUTRAL"),
        ("aim", "Enrollment was completed for a study that will measure survival on {drug}. Outcomes have yet to be reported.", "UNSUPPORTED"),
        ("prior", "Tumor regression followed irradiation. The oncologist later proposed starting {drug}.", "UNSUPPORTED"),
        ("safety", "The rash resolved after topical therapy. The patient was taking {drug}.", "UNSUPPORTED"),
        ("lab", "Cell survival decreased in an assay of {drug} activity.", "UNSUPPORTED"),
    ]
    pairs = [("A", "Tagrisso"), ("A", "osimertinib"), ("B", "lazertinib"), ("B", "Rybrevant")]
    for i, (kind, template, verdict) in enumerate(family):
        for product, drug in pairs:
            row = {"product": product, "text": template.format(drug=drug)}
            units = shortlist(row, broad=True)
            if not units:
                continue
            # In the progression example the named sentence itself states the new lesions.
            target = {"verdict": verdict, "unit": -1 if verdict == "UNSUPPORTED" else units[0][1],
                      "strength": "ordinary"}
            yield {"id": f"synthetic-{i}-{drug}", "provenance": f"controlled synthetic {kind} family",
                   "verdict": verdict,
                   "messages": [{"role": "user", "content": make_prompt(row, units, True)},
                                {"role": "assistant", "content": json.dumps(target)}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    original = load_rows(args.original / "train.jsonl")
    valid = load_rows(args.original / "valid.jsonl")
    pool = indexed("out/silver/pool.full.jsonl")
    reserved = [pool[record["id"]] for record in valid]
    for path in ("data/dev.full.jsonl", "out/silver/holdout.full.jsonl"):
        reserved.extend(load_rows(path))
    excluded_trials = set().union(*(trial_ids(row) for row in reserved))
    filtered = [record for record in original if not trial_ids(pool[record["id"]]) & excluded_trials
                and verified(pool[record["id"]], record)]
    examples = filtered + list(contrasts())
    random.Random(1984).shuffle(examples)
    args.out.mkdir(parents=True, exist_ok=True)
    write_atomic(args.out / "train.jsonl", "".join(json.dumps(r) + "\n" for r in examples))
    write_atomic(args.out / "valid.jsonl", (args.original / "valid.jsonl").read_text())
    print(f"Retained {len(filtered)}/{len(original)} teacher rows and added {len(examples)-len(filtered)} synthetic rows")
    print(dict(Counter(r["verdict"] for r in examples)))


if __name__ == "__main__":
    main()
