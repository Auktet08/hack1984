"""Write UI-ready label files: item fields + predicted labels + meta, one JSON object per line.

  python3 src/inference/export_labels.py            # all splits -> out/labels/{dev,unlabeled,test}.jsonl
  python3 src/inference/export_labels.py --splits dev unlabeled

Format: see LABELS.md. Today the labels come from the rules predictor (level 3). When the model path
lands, this script switches to it and the file format stays the same.
Standard library only; runs offline in about a second.
"""
import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TRACK = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(TRACK, "src", "rules"))
from predict import ASP, predict  # noqa: E402

SPLITS = {"dev": "dev.full.jsonl", "unlabeled": "unlabeled.full.jsonl", "test": "test_inputs.full.jsonl"}
ITEM_FIELDS = ["item_id", "source", "url", "published", "product", "title", "text"]
LEVEL = 3
BY = f"rules-L{LEVEL}"
# Placeholder confidence by source: rules are near-deterministic on these sources and guess on the rest.
# Replaced by source prior + rules/model agreement once the model path exists (PROBLEM.md §4.1).
CONF = {"ctgov": 0.9, "fda_event": 0.9, "fda_notice": 0.9, "fda_label": 0.7}
CONF_DEFAULT = 0.5


def export(split, out_dir):
    src = os.path.join(TRACK, "data", SPLITS[split])
    dst = os.path.join(out_dir, f"{split}.jsonl")
    n, dropped = 0, 0
    with open(src, encoding="utf-8") as f, open(dst + ".tmp", "w", encoding="utf-8") as g:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            label = predict(item, LEVEL)
            text = item.get("text") or ""
            for a in ASP:  # citation guarantee: every span is an exact substring of text
                if label[a] and label[a]["span"] not in text:
                    label[a], dropped = None, dropped + 1
            row = {k: item.get(k) for k in ITEM_FIELDS}
            row.update({k: label[k] for k in ["signal_type", "actionable", *ASP]})
            row["meta"] = {"by": BY, "confidence": CONF.get(item["source"], CONF_DEFAULT)}
            g.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    os.replace(dst + ".tmp", dst)  # readers never see a half-written file
    return dst, n, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", nargs="+", choices=list(SPLITS), default=list(SPLITS))
    ap.add_argument("--out", default=os.path.join(TRACK, "out", "labels"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for split in a.splits:
        dst, n, dropped = export(split, a.out)
        rows = [json.loads(l) for l in open(dst, encoding="utf-8")]
        aspects = Counter(x for r in rows for x in ASP if r[x])
        print(f"{split:9s} {n:5d} items -> {os.path.relpath(dst, TRACK)}  "
              f"actionable={sum(r['actionable'] == 'yes' for r in rows)}  "
              f"with_aspect={sum(any(r[x] for x in ASP) for r in rows)}  aspects={dict(aspects)}"
              + (f"  dropped_bad_spans={dropped}" if dropped else ""))


if __name__ == "__main__":
    main()
