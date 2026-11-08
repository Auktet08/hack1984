"""Fit heads on the silver pool, then score policies on the silver holdout and dev."""
import argparse
import json
import pickle
import random
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from heads import MODEL_SOURCES, Heads, UnitScorer, compose, load  # noqa: E402
from embed import Embedder  # noqa: E402

ROOT = HERE.parents[1]
score = runpy.run_path(str(ROOT / "scoring/score.py"))["score"]


def idx(rows):
    return {r["item_id"]: r for r in rows}


def paired(gold, items, base, cand, repeats=300):
    rng = random.Random(1984)
    keys = sorted(gold)
    wins = 0
    for _ in range(repeats):
        pairs = list(enumerate(rng.choices(keys, k=len(keys))))
        g = {i: gold[k] for i, k in pairs}
        it = {i: items[k] for i, k in pairs}
        wins += score(g, {i: cand[k] for i, k in pairs}, it)["composite"] > \
            score(g, {i: base[k] for i, k in pairs}, it)["composite"]
    return wins / repeats


def datasets():
    silver_labels = idx(load(ROOT / "silver/unlabeled_gemini.checked.jsonl"))
    silver_items = load(ROOT / "out/v2/silver_items.full.jsonl")
    holdout_ids = {r["item_id"] for r in load(ROOT / "out/silver/holdout.full.jsonl")}
    pool = [r for r in silver_items if r["item_id"] not in holdout_ids and r["source"] in MODEL_SOURCES]
    holdout = [r for r in silver_items if r["item_id"] in holdout_ids]
    dev = load(ROOT / "data/dev.full.jsonl")
    dev_gold = idx(load(ROOT / "data/dev.jsonl"))
    return silver_labels, pool, holdout, dev, dev_gold


SHORT = ("composite", "signal_macro_f1", "actionable_f1", "aspect_f1", "polarity_qwk", "span_f1", "n_aspects_matched")


def report(name, gold, items, pred, base=None, paired_runs=0):
    s = score(gold, pred, items)
    line = {k: s[k] for k in SHORT}
    if base is not None and paired_runs:
        line["paired_win"] = paired(gold, items, base, pred, paired_runs)
    print(f"{name:28s}", json.dumps(line), flush=True)
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=18090)
    ap.add_argument("--raw", type=Path, default=ROOT / "out/v2/raw.pkl")
    ap.add_argument("--refit", action="store_true")
    ap.add_argument("--C-item", type=float, default=1.0)
    ap.add_argument("--C-sent", type=float, default=1.0)
    ap.add_argument("--C-pol", type=float, default=1.0)
    args = ap.parse_args()
    labels, pool, holdout, dev, dev_gold = datasets()
    emb = Embedder(args.port, ROOT / "out/v2/emb")
    if args.refit or not args.raw.exists():
        heads = Heads(emb, args.C_item, args.C_sent, args.C_pol).fit(pool, labels)
        heads.units = UnitScorer(emb).fit(pool, labels, runpy.run_path(str(ROOT / "scoring/score.py"))["span_f1"])
        raw = {"holdout": heads.infer(holdout), "dev": heads.infer(dev)}
        emb.save()
        heads.emb = heads.units.emb = None
        with open(args.raw, "wb") as f:
            pickle.dump({"raw": raw, "heads": heads}, f)
    with open(args.raw, "rb") as f:
        saved = pickle.load(f)
    print(len(pool), "train items")
    return saved


if __name__ == "__main__":
    main()
