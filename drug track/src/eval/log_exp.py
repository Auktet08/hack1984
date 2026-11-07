"""Append one experiment row to docs/experiments/log.md from a score.py JSON output.

  python3 "drug track/src/eval/log_exp.py" --score "drug track/out/dev/score_L3.json" \
      --change "what changed" --verdict kept|reverted|superseded|info [--note "why / what we learned"]

Assigns the next E### id. Run solution/score_dev.sh first so the score file is fresh.
"""
import argparse
import datetime
import json
import os
import re

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "docs", "experiments", "log.md")
MARK = "<!-- new rows above this line -->"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", required=True)
    ap.add_argument("--change", required=True)
    ap.add_argument("--verdict", required=True, choices=["kept", "reverted", "superseded", "info"])
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    s = json.load(open(a.score))
    al, hu = s["all"], s.get("human_reviewed_only", {})
    log = open(LOG, encoding="utf-8").read()
    ids = [int(x) for x in re.findall(r"^\| E(\d{3}) ", log, re.M)]
    eid = f"E{(max(ids) + 1 if ids else 1):03d}"
    f = lambda v: "—" if v is None else f"{v:.3f}"
    row = (f"| {eid} | {datetime.date.today()} | {a.change} | {f(al['composite'])} | {f(hu.get('composite'))} | "
           f"{f(al['signal_macro_f1'])} | {f(al['actionable_f1'])} | {f(al['aspect_f1'])} | {f(al['polarity_qwk'])} | "
           f"{f(al['span_f1'])} | {a.verdict} | {a.note} |")
    open(LOG, "w", encoding="utf-8").write(log.replace(MARK, row + "\n" + MARK))
    print(row)


if __name__ == "__main__":
    main()
