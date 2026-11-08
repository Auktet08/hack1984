"""Coordinate-ascent tuning of composition policy on silver-pool out-of-fold outputs; report holdout and dev."""
import copy
import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from experiment import ROOT, datasets, idx, report, score  # noqa: E402
from heads import ASP, compose, load  # noqa: E402

SRC = ("pubmed", "news", "press_release")


def pool_score(policy, pool, raw, gold):
    return score(gold, compose(pool, raw, policy), idx(pool))["composite"]


def main():
    labels, pool, holdout, dev, dev_gold = datasets()
    oof = pickle.load(open(ROOT / "out/v2/oof.pkl", "rb"))["raw"]
    pool_gold = {r["item_id"]: labels[r["item_id"]] for r in pool}
    policy = {"base": "l4", "aspect_sources": SRC, "unit_scorer": True,
              "presence": {a: 0.5 for a in ASP}, "polarity_mode": "argmax"}
    best = pool_score(policy, pool, oof, pool_gold)
    print("start pool", round(best, 4), flush=True)
    grid = {f"presence.{a}": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01] for a in ASP}
    grid["polarity_mode"] = ["argmax", "expected"]
    grid["keep_rules"] = [True, False]
    grid["actionable"] = [None, 0.3, 0.35, 0.4, 0.5]
    for sweep in range(2):
        for key, values in grid.items():
            scores = []
            for v in values:
                cand = copy.deepcopy(policy)
                if key.startswith("presence."):
                    cand["presence"][key.split(".")[1]] = v
                elif key == "actionable":
                    if v is None:
                        cand.pop("actionable_sources", None)
                    else:
                        cand["actionable_sources"], cand["actionable_threshold"] = SRC, v
                else:
                    cand[key] = v
                scores.append((pool_score(cand, pool, oof, pool_gold), v, cand))
            s, v, cand = max(scores, key=lambda x: x[0])
            if s > best + 1e-4:
                best, policy = s, cand
            print(f"sweep {sweep} {key}: " + " ".join(f"{vv}:{ss:.4f}" for ss, vv, _ in scores) + f" -> best {best:.4f}",
                  flush=True)
    out = {k: v for k, v in policy.items()}
    out["aspect_sources"] = list(SRC)
    if "actionable_sources" in out:
        out["actionable_sources"] = list(SRC)
    Path(ROOT / "out/v2/policy-tuned.json").write_text(json.dumps(out, indent=1))
    print("tuned policy", json.dumps(out))
    saved = pickle.load(open(ROOT / "out/v2/raw.pkl", "rb"))
    raw = saved["raw"]
    shipped_h = idx(load(ROOT / "out/review/lora-guide-signal-silver.jsonl"))
    shipped_d = idx(load(ROOT / "out/review/lora-guide-signal-dev.jsonl"))
    model_signal = {k: v["signal_type"] for k, v in {**shipped_h, **shipped_d}.items()}
    hold_gold = {r["item_id"]: labels[r["item_id"]] for r in holdout}
    for name, pol in (("candidate A", {"base": "l4", "aspect_sources": SRC, "unit_scorer": True}), ("tuned", policy)):
        pol = {**pol, "model_signal": model_signal}
        report(f"{name} holdout", hold_gold, idx(holdout), compose(holdout, raw["holdout"], pol), shipped_h, 300)
        report(f"{name} dev", dev_gold, idx(dev), compose(dev, raw["dev"], pol), shipped_d, 300)


if __name__ == "__main__":
    main()
