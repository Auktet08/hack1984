"""Label items with Rules L3 plus linear heads on local Qwen embeddings (loopback only).

Fit:     predict_v2.py fit  --policy out/v2/policy.json --heads out/v2/heads-final.pkl [--include-holdout]
Predict: predict_v2.py run ITEMS.jsonl OUT.jsonl --policy out/v2/policy.json --heads out/v2/heads-final.pkl
"""
import argparse
import json
import pickle
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from embed import Embedder  # noqa: E402
from heads import MODEL_SOURCES, Heads, UnitScorer, compose, load  # noqa: E402
from llm_feats import LLM, PolarityModel, PresenceStack  # noqa: E402

ROOT = HERE.parents[1]


def make_llm(args):
    return LLM(port=args.llm_port, cache=args.cache_root / "llm-cache")


def fit(args, policy):
    labels = {r["item_id"]: r for r in load(ROOT / "silver/unlabeled_gemini.checked.jsonl")}
    items = load(ROOT / "out/v2/silver_items.full.jsonl")
    holdout = {r["item_id"] for r in load(ROOT / "out/silver/holdout.full.jsonl")}
    rows = [r for r in items if r["source"] in MODEL_SOURCES and (args.include_holdout or r["item_id"] not in holdout)]
    if args.include_dev:
        labels.update({r["item_id"]: r for r in load(ROOT / "data/dev.jsonl")})
        rows += [r for r in load(ROOT / "data/dev.full.jsonl") if r["source"] in MODEL_SOURCES]
    emb = Embedder(args.port, ROOT / "out/v2/emb")
    C = policy.get("C", {})
    heads = Heads(emb, C.get("item", 1.0), C.get("sent", 1.0), C.get("pol", 1.0)).fit(rows, labels)
    heads.units = UnitScorer(emb, policy.get("unit_alpha", 3.0)).fit(
        rows, labels, runpy.run_path(str(ROOT / "scoring/score.py"))["span_f1"])
    pol_model = None
    if policy.get("llm_polarity"):
        pol_model = PolarityModel(LLM(port=args.llm_port)).fit(rows, labels).model
    emb.save()
    heads.emb = heads.units.emb = None
    with open(args.heads, "wb") as f:
        pickle.dump({"heads": heads, "polarity_model": pol_model, "train_items": len(rows),
                     "include_holdout": args.include_holdout}, f)
    print(f"fitted on {len(rows)} silver items -> {args.heads}")


def run(args, policy):
    rows = load(args.items)
    if len({r["item_id"] for r in rows}) != len(rows) or any(not r.get("text") for r in rows):
        raise SystemExit("Inputs must have unique item IDs and complete text")
    with open(args.heads, "rb") as f:
        saved = pickle.load(f)
    heads = saved["heads"]
    if policy.get("llm_polarity"):
        if saved.get("polarity_model") is None:
            raise SystemExit("Policy needs the LLM polarity model; refit the heads with this policy")
        pm = PolarityModel(make_llm(args))
        pm.model = saved["polarity_model"]
        policy["polarity_model"] = pm
    heads.emb = heads.units.emb = Embedder(args.port, args.cache_root / "emb")
    model_rows = [r for r in rows if r["source"] in MODEL_SOURCES]
    raw = heads.infer(model_rows)
    heads.emb.save()
    pred = compose(rows, raw, policy, heads)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(pred[r["item_id"]], ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(args.out)
    print(f"{len(rows)} rows, {len(model_rows)} with model heads -> {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["fit", "run"])
    ap.add_argument("items", nargs="?")
    ap.add_argument("out", nargs="?", type=Path)
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--heads", type=Path, required=True)
    ap.add_argument("--port", type=int, default=18090, help="Embedding server (base GGUF, --embedding --pooling mean)")
    ap.add_argument("--llm-port", type=int, default=18080, help="Chat server (base GGUF) for polarity ratings")
    ap.add_argument("--include-holdout", action="store_true")
    ap.add_argument("--cache-root", type=Path, default=ROOT / "out/v2", help="Where embedding and LLM score caches live")
    ap.add_argument("--include-dev", action="store_true", help="Also train on dev gold (dev scores then no longer clean)")
    args = ap.parse_args()
    policy = json.loads(args.policy.read_text())
    for key in ("signal_sources", "actionable_sources", "aspect_sources", "signal_from",
                "llm_signal_sources", "llm_signal_efficacy_sources"):
        if key in policy and policy[key] is not None:
            policy[key] = tuple(policy[key])
    if policy.get("model_signal_file"):
        # Signal labels from the shipped guided LoRA run (applied only where L3 says efficacy on pubmed/news).
        policy["model_signal"] = {r["item_id"]: r["signal_type"] for r in load(ROOT / policy["model_signal_file"])}
    if policy.get("llm_signal_sources") or policy.get("llm_signal_efficacy_sources"):
        policy["llm"] = make_llm(args)
    if policy.get("presence_stack_files"):
        # Stack of embedding presence + local-Qwen item-level yes/no, fit on silver-pool out-of-fold presence.
        stacks = {}
        for aspect, path in policy["presence_stack_files"].items():
            st = PresenceStack(make_llm(args), aspect)
            st.model = pickle.load(open(ROOT / path, "rb"))
            stacks[aspect] = st
        policy["presence_stack"] = stacks
    fit(args, policy) if args.mode == "fit" else run(args, policy)


if __name__ == "__main__":
    main()
