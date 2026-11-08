#!/usr/bin/env bash
# Usage: run_offline.sh ITEMS.jsonl PREDICTIONS.jsonl [predictor options]
set -euo pipefail
track="$(cd "$(dirname "$0")" && pwd)"
predictor=(python3 "$track/src/inference/predict_full.py" --cache "$track/out/model_cache" "$@")
if [[ "$(uname -s)" == Darwin ]]; then
  profile='(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:*"))'
  exec sandbox-exec -p "$profile" "${predictor[@]}"
fi
exec "${predictor[@]}"
