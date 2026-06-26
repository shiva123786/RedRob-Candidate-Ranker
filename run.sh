#!/usr/bin/env bash
# One-command run: rank the candidate pool, then serve the dashboard.
#
# Usage:
#   ./run.sh ./data/candidates.jsonl
#   ./run.sh ./data/candidates.jsonl.gz --port 5050
set -euo pipefail

CANDIDATES_PATH="${1:-./data/candidates.jsonl}"
shift || true

if [ ! -f "$CANDIDATES_PATH" ]; then
  echo "Candidates file not found: $CANDIDATES_PATH" >&2
  echo "Usage: ./run.sh /path/to/candidates.jsonl[.gz]" >&2
  exit 1
fi

mkdir -p output dashboard/data

echo "==> Ranking candidates from $CANDIDATES_PATH"
python3 rank.py \
  --candidates "$CANDIDATES_PATH" \
  --out output/submission.csv \
  --json-out output/results.json \
  --meta-out output/run_meta.json

cp output/results.json dashboard/data/results.json
cp output/run_meta.json dashboard/data/run_meta.json

echo "==> Validating submission format"
python3 validate_submission.py output/submission.csv

echo "==> Starting dashboard"
python3 serve.py "$@"
