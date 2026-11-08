"""Select model field groups with the paired silver and dev handoff gates."""
import argparse
import json
import random
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/inference"))
from predict_full import ASP, GROUPS, load_rows, predict

score = runpy.run_path(str(ROOT / "scoring/score.py"))["score"]
FIELDS = {"aspects": ASP, "signal": ["signal_type"], "actionable": ["actionable"]}


def indexed(path):
    return {r["item_id"]: r for r in load_rows(path)}


def proposal(current, candidate, group):
    return {key: {**row, **{f: candidate[key][f] for f in FIELDS[group]}}
            for key, row in current.items()}


def paired_gain(gold, items, base, candidate, repeats=1000):
    rng = random.Random(1984)
    keys = sorted(gold)
    wins = 0
    for _ in range(repeats):
        pairs = list(enumerate(rng.choices(keys, k=len(keys))))
        sample = {i: gold[k] for i, k in pairs}
        sample_items = {i: items[k] for i, k in pairs}
        before = score(sample, {i: base[k] for i, k in pairs}, sample_items)["composite"]
        after = score(sample, {i: candidate[k] for i, k in pairs}, sample_items)["composite"]
        wins += after > before
    return wins / repeats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dev_candidate")
    ap.add_argument("silver_candidate")
    ap.add_argument("out", type=Path)
    ap.add_argument("--groups", nargs="+", choices=GROUPS, default=GROUPS)
    args = ap.parse_args()
    dev, silver = indexed("data/dev.full.jsonl"), indexed("out/silver/holdout.full.jsonl")
    dev_gold, silver_gold = indexed("data/dev.jsonl"), indexed("out/silver/holdout.gold.jsonl")
    dev_model, silver_model = indexed(args.dev_candidate), indexed(args.silver_candidate)
    current_dev = {k: predict(r, 3) for k, r in dev.items()}
    current_silver = {k: predict(r, 3) for k, r in silver.items()}
    reviewed = {k: r for k, r in dev_gold.items() if r.get("human_reviewed") or r.get("label_origin") == "reviewed_60"}
    groups = []
    args.out.mkdir(parents=True, exist_ok=True)
    for group in GROUPS:
        if group not in args.groups:
            continue
        next_dev = proposal(current_dev, dev_model, group)
        next_silver = proposal(current_silver, silver_model, group)
        before = score(dev_gold, current_dev, dev)
        after = score(dev_gold, next_dev, dev)
        changes = [(k, f) for k in dev for f in FIELDS[group] if current_dev[k][f] != next_dev[k][f]]
        correct = sum(
            (dev_gold[k][f] is not None and next_dev[k][f]["polarity"] == dev_gold[k][f]["polarity"])
            if group == "aspects" else next_dev[k][f] == dev_gold[k][f]
            for k, f in changes
        )
        accuracy = correct / len(changes) if changes else 0
        wins = paired_gain(silver_gold, silver, current_silver, next_silver)
        keep = wins >= 0.8 and after["composite"] >= before["composite"] - 0.02 and accuracy >= 0.6
        report = {"all": after, "human_reviewed_only": score(reviewed, next_dev, dev),
                  "dev_before": before["composite"], "silver_win_rate": wins,
                  "dev_changes": len(changes), "dev_correct": correct, "kept": keep}
        (args.out / f"{group}.json").write_text(json.dumps(report, indent=2) + "\n")
        print(group, json.dumps(report), flush=True)
        if keep:
            groups.append(group)
            current_dev, current_silver = next_dev, next_silver
    (args.out / "groups.json").write_text(json.dumps(groups) + "\n")
    selected = {
        "groups": groups,
        "dev": score(dev_gold, current_dev, dev),
        "human_reviewed_only": score(reviewed, current_dev, dev),
        "silver": score(silver_gold, current_silver, silver),
    }
    (args.out / "selected.json").write_text(json.dumps(selected, indent=2) + "\n")


if __name__ == "__main__":
    main()
