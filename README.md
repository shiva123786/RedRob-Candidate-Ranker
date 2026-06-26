# Redrob Candidate Ranker

A rule-based, fully explainable ranking engine for the **Redrob Intelligent
Candidate Discovery & Ranking Challenge** — plus a local dashboard to browse
the results.

```
recruiters using keyword filters → an HR Manager with 10 AI buzzwords on a skill list
this system                       → a Staff ML Engineer who actually built the thing
```

## Project layout

```
redrob-candidate-ranker/
├── rank.py                  # CLI entry point — produces submission.csv
├── validate_submission.py   # organizer-provided format validator
├── serve.py                 # serves the dashboard locally
├── run.sh                   # one command: rank + validate + serve
├── requirements.txt         # intentionally empty — stdlib only
├── engine/                  # the ranking engine (no dependencies)
│   ├── jd_knowledge.py      # every JD requirement, encoded as data
│   ├── features.py          # raw signal extraction per candidate
│   ├── scoring.py           # composite score + grounded reasoning text
│   └── honeypot.py          # hard safety filter
├── tests/
│   └── test_engine.py       # smoke tests for every trap category
├── output/                  # submission.csv / results.json / run_meta.json land here
└── dashboard/                # static site — Home / Rankings / Methodology
    ├── index.html
    ├── rankings.html
    ├── methodology.html
    ├── assets/css/styles.css
    ├── assets/js/{navbar,data,home,rankings}.js
    └── data/                 # results.json + run_meta.json the dashboard reads
```

Nothing here is one giant file: the navbar is one file shared by every page
(`assets/js/navbar.js`), each page has its own HTML + its own JS controller,
and the engine's four concerns (JD knowledge, feature extraction, scoring,
honeypot detection) are four separate modules.

## Quickstart
<img width="1902" height="953" alt="image" src="https://github.com/user-attachments/assets/1cd6b14a-0995-43fa-a599-d1e8550db09a" />

```bash
# 1. Rank the full candidate pool and write submission.csv
python3 rank.py --candidates ./data/candidates.jsonl \
                 --out output/submission.csv \
                 --json-out dashboard/data/results.json \
                 --meta-out dashboard/data/run_meta.json

# 2. Check the format
python3 validate_submission.py output/submission.csv

# 3. Browse the results
python3 serve.py
# → opens http://127.0.0.1:8000/index.html
```

Or all three in one go:

```bash
./run.sh ./data/candidates.jsonl
```

`candidates.jsonl.gz` works too — `rank.py` detects the `.gz` suffix and
streams it directly.

**Why `serve.py` instead of just opening `dashboard/index.html`:** the
dashboard fetches `data/results.json` with `fetch()`, which browsers refuse
to do over a bare `file://` URL (CORS). `serve.py` is a five-line wrapper
around Python's built-in `http.server` — no new dependency, just a local
file server.

## Why no ML libraries

Compute budget for ranking is CPU-only, ≤16GB RAM, ≤5 minutes, **no network**.
Given that, this submission deliberately uses zero embedding models and zero
LLM calls at rank time. Instead:

- **Stage 1 (lexical relevance)** does what an embeddings model would
  approximate, but as hand-weighted, capped regex matching against a
  vocabulary pulled directly from the JD. The cap (≤3 hits per concept
  bucket) is the same idea as BM25's term-frequency saturation — it's the
  mechanism that stops a keyword-stuffed profile from out-scoring a
  credible one just by repeating a buzzword.
- **Stage 2 (structured re-ranking)** is the part an embeddings-only system
  would miss entirely: title seniority, whether a claimed skill has any
  real tenure behind it, career-industry quality, logistics fit, and six
  explicit disqualifiers lifted straight from the JD's "things we explicitly
  do NOT want" section.
- **Stage 3 (behavioral modifier)** and **Stage 4 (honeypot filter)** are
  pure data hygiene — multiplicative availability adjustment, then a hard
  exclude for internally-impossible profiles.

Measured on the full 100,000-candidate file: **~130 seconds, ~210MB peak
RSS**. There's room to add a real embeddings-based Stage 1 within the
budget; this submission's bet is that for a structured, schema-rich
candidate pool (vs. open-domain text), curated lexical matching plus a
credibility-aware structured layer gets most of the value at a fraction of
the engineering and compute cost — and, unlike an embeddings score, every
number it produces can be explained in one sentence.
<img width="1896" height="961" alt="image" src="https://github.com/user-attachments/assets/abe65a2e-6b35-490a-8efa-b6d144cc05a2" />

## How the dataset's traps were identified

Before writing any scoring logic, the 100,000-candidate file was profiled
directly (see the heuristics' docstrings in `engine/honeypot.py` and
`engine/features.py` for the exact numbers):

- Only **852 of 100,000** candidates have an AI/ML-flavored title at all —
  confirms the JD's own note that this is a narrow profile in a big pool.
- Skill names cluster into four clean tiers by frequency: ~12% generic
  noise skills, ~5% "AI buzzword" skills (the keyword-stuffer cluster),
  ~1.3–1.4% genuine deep-ML skills (Python/PyTorch/vector-db/BM25 bundle),
  and a dozen skill phrases that appear **fewer than 8 times total** —
  these turned out to be 8 candidates who describe the JD's own mandate in
  plain language ("Vector Representations", "Content Matching") instead of
  buzzwords, the "Tier 5 plain-language" trap the spec describes.
- Honeypots were found, not guessed: three internal-consistency checks
  (expert-proficiency skill with ~0 months of use; `duration_months` that
  doesn't match `start_date`/`end_date`; total career months that don't
  match `years_of_experience`) each show a **clean bimodal split** on the
  real population — effectively zero false positives — and catch 60 of the
  documented ~80 honeypots.
<img width="1892" height="967" alt="image" src="https://github.com/user-attachments/assets/d618ae30-7fa1-4ee8-a19b-69137bd75b64" />

## Running the tests

```bash
python3 tests/test_engine.py
# or, if pytest is installed:
python3 -m pytest tests/ -v
```

Covers: honeypot detection (clean profile passes, each heuristic fires on a
constructed violation), a keyword-stuffer scoring low, a plain-language
strong candidate scoring well, and the no-visa-path disqualifier.

## Filling in `submission_metadata.yaml`

`submission_metadata.yaml` in this folder has the engine/compute/methodology
fields filled in already. You still need to fill in **team identity**,
**github_repo**, and **sandbox_link** before submitting — those are specific
to you and can't be filled in on your behalf.

## Known limitations / next steps

- The "pure academic research, no production deployment" disqualifier has
  low recall on this dataset — the dataset doesn't expose a `Research`/
  `Academia` industry value to key off, so it currently only fires on
  explicit academic-language cues (postdoc, academic lab, etc.) in the free
  text, which is a narrower net than the JD's own description implies.
- Company-name-based product-vs-services classification was deliberately
  *not* used (only the `industry` field was), since hardcoding which
  fictional/real company names in this specific file count as "good" would
  overfit to this dataset rather than generalizing to a new JD or a refreshed
  candidate pool.
- Honeypot recall is ~75% of the documented ~80 (60 found) via the three
  signals above. A fourth candidate heuristic — overlapping employment date
  ranges — was tested during dataset exploration and found zero hits on
  this file, so it was left out of `engine/honeypot.py` rather than shipped
  as dead weight; worth re-testing if the dataset is refreshed.

