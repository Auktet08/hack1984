"""Create deterministic silver hold-out and MLX chat training data."""
import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "inference"))
from predict_full import ASP, load_rows, prompt, split

TARGETS = {"pubmed": 60, "news": 30, "press_release": 15}


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def words(text):
    return re.findall(r"\w+", text.lower())


def align(row, label):
    units = split(row["text"])
    target = {k: label[k] for k in ("signal_type", "actionable")}
    target["aspects"] = []
    total = 0
    for aspect in ASP:
        a = label[aspect]
        if a is None:
            continue
        total += 1
        span = a["span"]
        start = row["text"].find(span)
        end = start + len(span)
        if start < 0:
            continue

        def overlap(unit):
            lo, hi = max(start, unit["start"]), min(end, unit["end"])
            return len(words(row["text"][lo:hi]))

        best = max(units, key=lambda unit: (overlap(unit), -len(unit["text"])))
        if 2 * overlap(best) >= max(1, len(words(best["text"]))):
            target["aspects"].append({"unit_id": best["id"], "aspect": aspect, "polarity": a["polarity"]})
    return {"messages": [{"role": "user", "content": prompt(row, units)},
                         {"role": "assistant", "content": json.dumps(target)}]}, total, len(target["aspects"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", help="Local tokenizer directory for the optional token limit")
    parser.add_argument("--max-tokens", type=int, default=1152)
    args = parser.parse_args()
    tokenizer = None
    if args.tokenizer:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    rng = random.Random(1984)
    labels = {r["item_id"]: r for r in load_rows("silver/unlabeled_gemini.checked.jsonl")}
    test_sets = [set(words(r["text"])) for r in load_rows("data/test_inputs.full.jsonl")]
    strata = defaultdict(list)
    dropped = []
    for r in load_rows("data/unlabeled.full.jsonl"):
        if r["item_id"] not in labels:
            continue
        if not r.get("text") or hashlib.sha256(r["text"].encode()).hexdigest() != r["text_sha256"]:
            dropped.append(r["item_id"])
            continue
        tokens = set(words(r["text"]))
        if any(5 * len(tokens & test) >= 4 * len(tokens | test) for test in test_sets):
            dropped.append(r["item_id"])
            continue
        strata[r["source"], r["product"]].append(r)
    holdout, pool = [], []
    for source in sorted({source for source, _ in strata}):
        groups = [v for (s, _), v in sorted(strata.items()) if s == source]
        size = sum(map(len, groups))
        target = TARGETS.get(source, 0)
        exact = [target * len(g) / size for g in groups]
        quotas = list(map(int, exact))
        remainder = sorted(range(len(groups)), key=lambda i: exact[i] - quotas[i], reverse=True)
        for i in remainder[:target - sum(quotas)]:
            quotas[i] += 1
        for group, quota in zip(groups, quotas):
            rng.shuffle(group)
            holdout.extend(group[:quota])
            pool.extend(group[quota:])
    for name, rows in (("holdout", holdout), ("pool", pool)):
        write(Path(f"out/silver/{name}.full.jsonl"), rows)
        write(Path(f"out/silver/{name}.gold.jsonl"), (labels[r["item_id"]] for r in rows))
    rng.shuffle(pool)
    cutoff = max(1, len(pool) // 20)
    total = kept = 0
    for name, rows in (("valid", pool[:cutoff]), ("train", pool[cutoff:])):
        output = []
        for row in rows:
            example, found, mapped = align(row, labels[row["item_id"]])
            total += found
            kept += mapped
            output.append(example)
            if name == "train" and row["source"] in {"news", "press_release"}:
                output.append(example)
        rng.shuffle(output)
        write(Path(f"out/lora_data/{name}.jsonl"), output)
        print(name, len(output))
        if tokenizer is not None:
            short = [row for row in output if len(tokenizer.apply_chat_template(
                row["messages"], return_dict=False
            )) <= args.max_tokens]
            write(Path(f"out/lora_short/{name}.jsonl"), short)
            print(f"{name} within {args.max_tokens} tokens: {len(short)}/{len(output)}")
    print("Excluded IDs:", dropped)
    print("Holdout:", dict(Counter(r["source"] for r in holdout)))
    print(f"Mapped {kept}/{total} aspects ({kept / total:.1%})")


if __name__ == "__main__":
    main()
