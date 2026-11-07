#!/usr/bin/env bash
# Score rules levels on dev and print a comparison table.
#   drug\ track/src/eval/score_dev.sh [levels...]   (default: 1 2 3)
# Outputs: drug track/out/dev/dev_L<N>.jsonl and score_L<N>.json. Log results with log_exp.py.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$(cd "$HERE/../.." && pwd)"
OUT="$PKG/out/dev"
mkdir -p "$OUT"
LEVELS=("${@:-1 2 3}")
for lvl in ${LEVELS[*]}; do
  python3 -I "$PKG/src/rules/predict.py" "$PKG/data/dev.full.jsonl" "$OUT/dev_L$lvl.jsonl" --level "$lvl"
  python3 -I "$PKG/scoring/score.py" --gold "$PKG/data/dev.jsonl" --pred "$OUT/dev_L$lvl.jsonl" \
    --items "$PKG/data/dev.full.jsonl" > "$OUT/score_L$lvl.json"
done
python3 -I - "$OUT" ${LEVELS[*]} <<'EOF'
import json, sys, os
out, levels = sys.argv[1], sys.argv[2:]
keys = ["signal_macro_f1", "actionable_f1", "aspect_f1", "polarity_qwk", "speaker_accuracy", "span_f1",
        "citation_validity", "n_aspects_matched", "composite"]
res = [json.load(open(os.path.join(out, f"score_L{l}.json"))) for l in levels]
print(f"{'metric':20}" + "".join(f"{'L' + l:>9}" for l in levels))
for k in keys:
    print(f"{k:20}" + "".join(f"{(r['all'][k] if r['all'][k] is not None else float('nan')):>9.3f}" for r in res))
print(f"{'composite (human)':20}" + "".join(f"{r['human_reviewed_only']['composite']:>9.3f}" for r in res))
EOF
