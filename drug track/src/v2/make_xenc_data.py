"""Build yes/no cross-encoder data for aspect sentence location from the silver pool (hard negatives from OOF locator)."""
import json, pickle, random, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from experiment import ROOT, datasets
from heads import ASP, span_sentence
from embed import sentences
from llm_feats import ASPECT_HINT
from predict_full import PRODUCT_NAMES


def xenc_prompt(row, aspect, sentence):
    return (f"Target drug: {PRODUCT_NAMES.get(row['product'], row['product'])}. Source: {row['source']}.\n"
            f"Title: {row['title'][:200]}\nSentence: {sentence}\n"
            f"Does this sentence state the item's judgment of the target drug on {ASPECT_HINT[aspect]}? Answer yes or no.")


def main(k_neg=3, out=ROOT / "out/v2/xenc-data"):
    labels, pool, holdout, dev, dev_gold = datasets()
    oof = pickle.load(open(ROOT / "out/v2/oof.pkl", "rb"))["raw"]
    rng = random.Random(1984)
    rows = []
    for r in pool:
        info = oof.get(r["item_id"])
        if not info:
            continue
        sents = sentences(r)
        for a in ASP:
            g = labels[r["item_id"]][a]
            if not g or a not in info["aspects"]:
                continue
            j = span_sentence(r, g["span"], sents)
            if j is None:
                continue
            la = np.array(info["aspects"][a]["loc_all"])
            negs = [int(i) for i in np.argsort(-la) if int(i) != j][:k_neg]
            rows.append({"messages": [{"role": "user", "content": xenc_prompt(r, a, sents[j]["text"])},
                                      {"role": "assistant", "content": "yes"}], "group": r["item_id"]})
            for i in negs:
                rows.append({"messages": [{"role": "user", "content": xenc_prompt(r, a, sents[i]["text"])},
                                          {"role": "assistant", "content": "no"}], "group": r["item_id"]})
    groups = sorted({x["group"] for x in rows}); rng.shuffle(groups)
    valid_g = set(groups[:40])
    out.mkdir(parents=True, exist_ok=True)
    for name, sel in (("train", [x for x in rows if x["group"] not in valid_g]), ("valid", [x for x in rows if x["group"] in valid_g])):
        rng.shuffle(sel)
        (out / f"{name}.jsonl").write_text("".join(json.dumps({"messages": x["messages"]}) + "\n" for x in sel))
        print(name, len(sel), sum(x["messages"][1]["content"] == "yes" for x in sel), "yes")


if __name__ == "__main__":
    main()
