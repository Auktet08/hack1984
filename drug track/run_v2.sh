#!/usr/bin/env bash
# v2 offline labeler: Rules L3 + L4 silver-pool rules + linear heads on local Qwen3.5-2B embeddings
# + local Qwen polarity/signal scoring. Network is denied except loopback.
#
# Needs two loopback servers from the same base GGUF (models/qwen35-2b-base.q8_0.gguf):
#   llama-server -m models/qwen35-2b-base.q8_0.gguf --jinja --host 127.0.0.1 --port 18080 -c 8192 --parallel 1 --cache-ram 0
#   llama-server -m models/qwen35-2b-base.q8_0.gguf --embedding --pooling mean --host 127.0.0.1 --port 18090 -c 8192 -b 4096 -ub 4096
# The policy also reads the v1 guided-LoRA signal labels (out/submission.v1-hybrid.jsonl, made by run_offline.sh --model-signal).
#
# Usage: run_v2.sh ITEMS.jsonl PREDICTIONS.jsonl [--policy out/v2/policy-f.json] [--heads out/v2/heads-e-all.pkl]
set -euo pipefail
track="$(cd "$(dirname "$0")" && pwd)"
cd "$track"
items="$1"; out="$2"; shift 2
policy=out/v2/policy-f.json
heads=out/v2/heads-e-all.pkl
while [[ $# -gt 0 ]]; do
  case "$1" in
    --policy) policy="$2"; shift 2 ;;
    --heads) heads="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
cmd=(out/mac/venv/bin/python src/v2/predict_v2.py run "$items" "$out" --policy "$policy" --heads "$heads")
if [[ "$(uname -s)" == Darwin ]]; then
  profile='(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:*"))'
  exec sandbox-exec -p "$profile" "${cmd[@]}"
fi
exec "${cmd[@]}"
