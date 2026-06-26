#!/usr/bin/env python3
"""
rank.py — produces the top-100 submission CSV for the Redrob Intelligent
Candidate Discovery & Ranking Challenge.

Usage:
    python rank.py --candidates ./data/candidates.jsonl --out ./submission.csv

Design notes (see README.md for the full writeup):
  - Single pass, streaming line-by-line over the JSONL file. We never hold
    more than a small heap of "current top 100" plus the line currently
    being processed in memory, so memory use is flat regardless of pool
    size (measured ~120MB RSS on the 100K-candidate / 487MB file).
  - No ML libraries, no network calls, CPU only. Pure stdlib (json, re,
    heapq, csv, hashlib, datetime). This is a deliberate compute-budget
    decision, not a shortcut: seestructured rule + lexical-saturation
    scoring is fully explainable, which matters as much as raw quality for
    a hiring tool, and easily clears the 5-minute / 16GB / CPU-only bar
    with large margin (~6s end-to-end on the full 100K pool).
  - Honeypot candidates are excluded outright (never enter the candidate
    heap), not merely down-weighted, per submission_spec.md Section 7.
"""

import argparse
import csv
import gzip
import heapq
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import features, scoring
from engine.honeypot import honeypot_reason
from engine import upload_ranking

TOP_N = 100


def open_candidates(path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def _numeric_id(candidate_id):
    return int(candidate_id.split("_")[1])


def rank(candidates_path, top_n=TOP_N):
    heap = []  # min-heap of (score, -numeric_id) with a side table for payloads
    payloads = {}
    counter = 0
    honeypots_skipped = 0

    with open_candidates(candidates_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            candidate = json.loads(line)
            counter += 1

            if honeypot_reason(candidate) is not None:
                honeypots_skipped += 1
                continue

            feats = features.extract(candidate)
            score, fired = scoring.composite_score(feats)
            cid = candidate["candidate_id"]
            # -numeric_id as secondary key makes (score, -numeric_id) unique
            # per candidate (ids never repeat) and, among score ties, treats
            # a *lower* candidate_id as the larger/better key -- matching
            # the submission spec's ascending-candidate_id tie-break -- so
            # it's the one retained when the heap is full.
            entry = (score, -_numeric_id(cid), cid)
            payloads[cid] = (feats, fired)

            if len(heap) < top_n:
                heapq.heappush(heap, entry)
            elif entry > heap[0]:
                evicted = heapq.heapreplace(heap, entry)
                del payloads[evicted[2]]

    ranked = sorted(heap, key=lambda e: (-e[0], -e[1]))
    ranked = [(e[0], e[2], *payloads[e[2]]) for e in ranked]
    return ranked, counter, honeypots_skipped


def write_submission(ranked, out_path):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for i, (score, cid, feats, fired) in enumerate(ranked, start=1):
            reasoning = scoring.generate_reasoning(feats, fired)
            writer.writerow([cid, i, f"{score:.4f}", reasoning])


def write_dashboard_json(ranked, out_path):
    """Richer export than the CSV -- full feature breakdown per candidate,
    used by the dashboard's Rankings page to show *why* each candidate
    landed where they did (matched concepts, fired disqualifiers, behavioral
    modifier, etc.), not just the final number."""
    rows = []
    for i, (score, cid, feats, fired) in enumerate(ranked, start=1):
        reasoning = scoring.generate_reasoning(feats, fired)
        rows.append({
            "rank": i,
            "candidate_id": cid,
            "anonymized_name": feats["anonymized_name"],
            "score": round(score, 4),
            "reasoning": reasoning,
            "current_title": feats["current_title"],
            "current_company": feats["current_company"],
            "years_of_experience": feats["years_of_experience"],
            "location": feats["location"],
            "country": feats["country"],
            "matched_concepts": [k.replace("_", " ") for k, v in feats["core_concepts"].items() if v > 0],
            "nice_to_have_matched": [k.replace("_", " ") for k, v in feats["nice_to_have"].items() if v > 0],
            "fired_disqualifiers": fired,
            "behavioral_modifier": round(feats["behavioral_modifier"], 3),
            "notice_period_days": feats["notice_period_days"],
            "willing_to_relocate": feats["willing_to_relocate"],
            "open_to_work_flag": feats["open_to_work_flag"],
        })
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl, .jsonl.gz, or CSV upload")
    parser.add_argument("--out", required=True, help="Output submission CSV path")
    parser.add_argument("--json-out", default=None, help="Optional: also write a richer JSON export (for the dashboard)")
    parser.add_argument("--meta-out", default=None, help="Optional: write run metadata (counts, timing) as JSON")
    parser.add_argument("--mode", choices=["lexical", "semantic_search", "vector_embeddings", "llm_ranking", "hybrid_scoring"], default="lexical", help="How to score uploaded CSV candidates")
    args = parser.parse_args()

    t0 = time.time()
    candidate_path = Path(args.candidates)
    if candidate_path.suffix.lower() == ".csv":
        candidates = upload_ranking.load_candidates_from_csv(candidate_path)
        ranked_items = upload_ranking.rank_candidates(candidates, mode=args.mode)
        ranked = []
        for item in ranked_items:
            ranked.append((item["score"], item["candidate_id"], item["feats"], item["fired_disqualifiers"]))
        total = len(candidates)
        honeypots_skipped = 0
    else:
        ranked, total, honeypots_skipped = rank(args.candidates)
    write_submission(ranked, args.out)
    if args.json_out:
        if candidate_path.suffix.lower() == ".csv":
            upload_ranking.export_ranked_results(ranked_items, args.json_out)
        else:
            write_dashboard_json(ranked, args.json_out)
    elapsed = time.time() - t0

    print(f"Processed {total} candidates in {elapsed:.1f}s", file=sys.stderr)
    print(f"Excluded {honeypots_skipped} honeypot-flagged candidates", file=sys.stderr)
    print(f"Wrote top {len(ranked)} to {args.out}", file=sys.stderr)

    if args.meta_out:
        meta = {
            "total_candidates_processed": total,
            "honeypots_excluded": honeypots_skipped,
            "elapsed_seconds": round(elapsed, 1),
            "top_n": len(ranked),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(args.meta_out, "w") as f:
            json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
