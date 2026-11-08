#!/usr/bin/env python3
"""Label a startup corpus (transcript turns, analog-launch items) with the current labeler backend.

    python3 "drug track/src/startup/label.py" --corpus odac            # poziotinib ODAC transcript turns
    python3 "drug track/src/startup/label.py" --corpus probe           # mobocertinib + poziotinib probe items
    python3 "drug track/src/startup/label.py" --corpus odac --limit 20 # smoke test

Output contract (what the UI and the analysis read): out/startup/labels/<corpus>.jsonl, one row per item with the
item fields (plus speaker fields for transcripts), the track labels (signal_type, actionable, five aspects with
span/polarity/speaker) and meta {labeler, model, stand_in, labeled_at}.

Use --backend local to label through a loopback llama-server. The default Gemini backend remains a public-data
stand-in, identified by meta.stand_in.

Only public material goes to Gemini (FDA transcript, public news and papers). Never test items, never customer data.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
OUTDIR = PKG / "out/startup/labels"
ASPECTS = ["efficacy", "safety", "convenience", "access_cost", "evidence_quality"]
FOCUS = {
    "poziotinib": "poziotinib (Spectrum Pharmaceuticals; HER2 exon 20 insertion NSCLC; FDA advisory committee "
                  "voted 9-4 against it on 22 Sep 2022)",
    "mobocertinib": "mobocertinib (Exkivity, TAK-788; Takeda; EGFR exon 20 insertion NSCLC; US accelerated "
                    "approval Sep 2021, withdrawn after EXCLAIM-2 in Oct 2023)",
}
CORPORA = {
    # name: (items file, product -> focus key, row filter)
    "odac": (PKG / "out/startup/poziotinib_odac_turns.jsonl", {"poziotinib": "poziotinib"},
             lambda r: r["words"] >= 15 and r["section"] not in ("introductions", "conflicts", "call_to_order")),
    "probe": (PKG / "out/startup/probe_items.jsonl", {"P": "poziotinib", "M": "mobocertinib"}, lambda r: True),
}


def load(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def run_gemini(items_path, out_path, focus, jobs):
    cmd = [sys.executable, str(PKG / "src/teacher/gemini_label.py"), "--backend", "api", "--thinking", "low",
           "--items", str(items_path), "--out", str(out_path), "--focus", focus, "--jobs", str(jobs)]
    subprocess.run(cmd, check=True)
    stats = json.load(open(str(out_path) + ".stats.json"))
    checked = {r["item_id"]: r for r in load(stats["checked_out"])}
    return checked, ",".join(stats["models_served"]) or "gemini", stats


def run_local(rows, focus, url, model):
    sys.path.insert(0, str(PKG / "src/inference"))
    from predict_full import label_local

    cache = PKG / "out/model_cache"
    cache.mkdir(parents=True, exist_ok=True)
    context = f"Target drug and setting: {focus}. Judge claims about this drug as stated by the source."
    labels = {r["item_id"]: label_local(r, url, model, cache, context) for r in rows}
    return labels, model, {"labeled": len(labels), "failed": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=sorted(CORPORA), required=True)
    ap.add_argument("--backend", choices=["gemini", "local"], default="gemini")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--local-url", default="http://127.0.0.1:18080/v1/chat/completions")
    ap.add_argument("--local-model", default="qwen3.5-2b")
    a = ap.parse_args()

    src, product_map, keep = CORPORA[a.corpus]
    rows = [r for r in load(src) if keep(r)][: a.limit or None]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    labels, stats_all = {}, {}
    for prod, focus_key in product_map.items():
        group = [dict(r, product=focus_key) for r in rows if r["product"] == prod]
        if not group:
            continue
        if a.backend == "local":
            got, model, stats = run_local(group, FOCUS[focus_key], a.local_url, a.local_model)
        else:
            items_path = OUTDIR / f"{a.corpus}_{focus_key}.items.jsonl"
            with open(items_path, "w") as f:
                for r in group:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            got, model, stats = run_gemini(items_path, OUTDIR / f"{a.corpus}_{focus_key}.gemini.jsonl",
                                           FOCUS[focus_key], a.jobs)
        labels.update({k: (v, model) for k, v in got.items()})
        stats_all[focus_key] = {k: stats[k] for k in ("labeled", "failed", "span_check", "tokens") if k in stats}

    out = OUTDIR / f"{a.corpus}.jsonl"
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    n = 0
    with open(out, "w") as fo:
        for r in rows:
            if r["item_id"] not in labels:
                continue
            lab, model = labels[r["item_id"]]
            prod = product_map[r["product"]]
            row = dict(r, product=prod, signal_type=lab["signal_type"], actionable=lab["actionable"],
                       **{x: lab[x] for x in ASPECTS},
                       meta={"labeler": "local" if a.backend == "local" else "gemini-stand-in",
                             "model": model, "stand_in": a.backend == "gemini",
                             "labeled_at": now})
            fo.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(json.dumps({"out": str(out), "rows": n, "of": len(rows), "runs": stats_all}, indent=2))


if __name__ == "__main__":
    main()
