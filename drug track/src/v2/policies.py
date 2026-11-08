"""Score composition policies from cached head outputs on silver holdout and dev."""
import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from experiment import ROOT, datasets, idx, report  # noqa: E402
from heads import compose, load  # noqa: E402
from embed import Embedder  # noqa: E402

ALL = ("pubmed", "news", "press_release")


def evaluate(policies, raw_path=ROOT / "out/v2/raw.pkl", paired_runs=0, port=18090):
    labels, pool, holdout, dev, dev_gold = datasets()
    saved = pickle.load(open(raw_path, "rb"))
    raw, heads = saved["raw"], saved["heads"]
    heads.emb = Embedder(port, ROOT / "out/v2/emb")
    if getattr(heads, "units", None):
        heads.units.emb = heads.emb
    hold_gold = {r["item_id"]: labels[r["item_id"]] for r in holdout}
    shipped_h = idx(load(ROOT / "out/review/lora-guide-signal-silver.jsonl"))
    shipped_d = idx(load(ROOT / "out/review/lora-guide-signal-dev.jsonl"))
    report("shipped holdout", hold_gold, idx(holdout), shipped_h)
    report("shipped dev", dev_gold, idx(dev), shipped_d)
    model_signal = {k: v["signal_type"] for k, v in {**shipped_h, **shipped_d}.items()}
    results = {}
    for name, policy in policies.items():
        if policy.pop("use_model_signal", False):
            policy["model_signal"] = model_signal
        ph = compose(holdout, raw["holdout"], policy, heads)
        pd = compose(dev, raw["dev"], policy, heads)
        sh = report(f"{name} holdout", hold_gold, idx(holdout), ph, shipped_h, paired_runs)
        sd = report(f"{name} dev", dev_gold, idx(dev), pd, shipped_d, paired_runs)
        results[name] = (sh, sd, ph, pd)
    heads.emb.save()
    return results


if __name__ == "__main__":
    policies = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "signal": {"signal_sources": ALL},
        "actionable": {"actionable_sources": ALL},
        "aspects": {"aspect_sources": ALL},
        "all": {"signal_sources": ALL, "actionable_sources": ALL, "aspect_sources": ALL},
    }
    evaluate(policies)
