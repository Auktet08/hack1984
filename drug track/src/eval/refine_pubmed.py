"""Score a focused PubMed efficacy pass against the selected hybrid."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from gate_local import indexed
from predict_full import PRODUCT_NAMES, call, split, trim, write_atomic

GUIDE = (
    "Evaluate only efficacy of the named target in this PubMed abstract. "
    "The abstract must explicitly report an outcome about the target, such as survival, response, "
    "disease progression, or a comparative efficacy result. A study objective, trial design, "
    "drug mention, treatment line, or mechanism of resistance alone is insufficient. "
    "An outcome that is comparable or unchanged has polarity 0. A rival outperforming the "
    "target is negative for the target. Increased survival or response is favorable, while "
    "increased progression is unfavorable. Use magnitude 2 only for clearly strong results, "
    "such as a statistically significant improvement or failure of a primary endpoint. "
    "Return an empty aspects list unless one evidence unit alone supports the rating. "
    "Return at most one aspect and use only efficacy. Signal and actionability are ignored."
)


def propose(row, cache):
    units = split(row["text"], max_words=32, separate_clauses=False)
    evidence = "\n".join(f'{u["id"]}: {u["text"]}' for u in units)
    target = PRODUCT_NAMES.get(row["product"], row["product"])
    message = (
        f"{GUIDE}\nTarget: {target}\nTitle: {row['title']}\n"
        'Return JSON with signal_type, actionable, and aspects containing unit_id, aspect and polarity.\n'
        f"Evidence units:\n{evidence}"
    )
    result = call("http://127.0.0.1:18083/v1/chat/completions", "qwen35-2b-lora-v1",
                  message, units, cache, plain=False)
    for aspect in result["aspects"]:
        if aspect["aspect"] == "efficacy":
            unit = units[aspect["unit_id"]]
            start, end = trim(row["text"], unit["start"], unit["end"])
            return {"speaker": "researcher", "span": row["text"][start:end],
                    "polarity": aspect["polarity"]}
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items")
    parser.add_argument("baseline")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    items, baseline = indexed(args.items), indexed(args.baseline)
    if items.keys() != baseline.keys():
        parser.error("Input and baseline IDs must match")
    cache = Path("out/model_cache")
    cache.mkdir(parents=True, exist_ok=True)
    eligible = [k for k, row in items.items() if row["source"] == "pubmed" and baseline[k]["efficacy"] is None]
    with ThreadPoolExecutor(max_workers=2) as pool:
        proposals = list(pool.map(lambda k: propose(items[k], cache), eligible))
    for key, label in zip(eligible, proposals):
        baseline[key]["efficacy"] = label
    write_atomic(args.output, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in baseline.values()))
    print(f"{len(eligible)} model calls, {sum(p is not None for p in proposals)} additions")


if __name__ == "__main__":
    main()
