# data/

Place the challenge's `candidates.jsonl` (or `candidates.jsonl.gz`) here
before running `rank.py` or `./run.sh`. It is not bundled in this repo —
it's the organizer-provided dataset (487MB uncompressed), not part of the
solution itself.

```bash
cp /path/to/candidates.jsonl ./data/candidates.jsonl
python3 rank.py --candidates ./data/candidates.jsonl --out output/submission.csv
```
