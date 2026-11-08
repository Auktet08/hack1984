"""Compare frozen predictions against a supplied release baseline."""
import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from gate_local import indexed, score
from predict_full import write_atomic

TRIAL = re.compile(r"\bNCT\d{8}\b", re.I)


def paired_report(gold, items, baseline, candidate, seed=1984, draws=1000):
    groups = defaultdict(list)
    for key in sorted(gold):
        row = items[key]
        trials = {trial.upper() for trial in TRIAL.findall(row["text"])}
        group = ("trial", next(iter(trials))) if row["source"] == "pubmed" and len(trials) == 1 else ("item", key)
        groups[group].append(key)
    blocks = list(groups.values())
    rng = random.Random(seed)
    deltas = []
    for _ in range(draws):
        sample = [key for block in rng.choices(blocks, k=len(blocks)) for key in block]
        sampled_gold, sampled_items, sampled_base, sampled_cand = [
            dict(enumerate(source[key] for key in sample)) for source in (gold, items, baseline, candidate)]
        before = score(sampled_gold, sampled_base, sampled_items)["composite"]
        after = score(sampled_gold, sampled_cand, sampled_items)["composite"]
        deltas.append(round(after - before, 4))
    deltas.sort()
    before = score(gold, baseline, items)
    after = score(gold, candidate, items)
    return {"baseline": before, "candidate": after, "delta": round(after["composite"] - before["composite"], 4),
            "changed_rows": sum(baseline[key] != candidate[key] for key in gold),
            "resample_unit": "shared single NCT ID for PubMed when available, otherwise item",
            "groups": len(blocks), "multi_item_groups": sum(len(block) > 1 for block in blocks),
            "draws": draws, "seed": seed, "positive_fraction": sum(x > 0 for x in deltas) / draws,
            "percentile_interval": [deltas[int((draws - 1) * p)] for p in (0.025, 0.975)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("gold", "items", "baseline", "candidate"):
        parser.add_argument(name)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    gold, items, baseline, candidate = map(indexed, (args.gold, args.items, args.baseline, args.candidate))
    if not gold or not all(x.keys() == gold.keys() for x in (items, baseline, candidate)):
        parser.error("All files must contain the same nonempty set of IDs")
    report = paired_report(gold, items, baseline, candidate)
    write_atomic(args.output, json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("baseline", "candidate")}))


if __name__ == "__main__":
    main()
