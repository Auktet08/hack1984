"""5-fold out-of-fold head outputs on the silver pool, for threshold and policy tuning on ~1,000 items."""
import pickle
import random
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from embed import Embedder  # noqa: E402
from experiment import ROOT, datasets  # noqa: E402
from heads import Heads, UnitScorer  # noqa: E402


def main(folds=5, out=ROOT / "out/v2/oof.pkl"):
    labels, pool, holdout, dev, dev_gold = datasets()
    emb = Embedder(18090, ROOT / "out/v2/emb")
    span_f1 = runpy.run_path(str(ROOT / "scoring/score.py"))["span_f1"]
    order = sorted(pool, key=lambda r: r["item_id"])
    random.Random(1984).shuffle(order)
    raw, models = {}, []
    for k in range(folds):
        test = order[k::folds]
        ids = {r["item_id"] for r in test}
        train = [r for r in order if r["item_id"] not in ids]
        heads = Heads(emb).fit(train, labels)
        heads.units = UnitScorer(emb).fit(train, labels, span_f1)
        raw.update(heads.infer(test))
        heads.emb = heads.units.emb = None
        models.append((sorted(ids), heads))
        print(f"fold {k}: {len(train)} train, {len(test)} oof", flush=True)
    emb.save()
    with open(out, "wb") as f:
        pickle.dump({"raw": raw, "folds": models}, f)


if __name__ == "__main__":
    main()
