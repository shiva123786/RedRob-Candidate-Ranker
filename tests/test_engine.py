"""
Smoke tests for the ranking engine, covering the specific trap categories
the challenge dataset is designed to test for:
  - honeypot detection (3 heuristics) has zero false positives on
    well-formed synthetic profiles
  - a keyword-stuffer (irrelevant title, every JD buzzword on the skill
    list, no real tenure behind any of them) scores low
  - a "plain-language" candidate (no buzzwords, but describes the actual
    work in their own words) scores competitively
  - the no-visa-path disqualifier fires correctly

Run with pytest if available (`python -m pytest tests/ -v`), or directly
with `python tests/test_engine.py` -- no third-party dependencies needed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import features, scoring, upload_ranking
from engine.honeypot import honeypot_reason


def _base_candidate(**overrides):
    candidate = {
        "candidate_id": "CAND_0000001",
        "profile": {
            "anonymized_name": "Test Candidate",
            "headline": "Engineer",
            "summary": "Generic professional summary.",
            "location": "Bangalore, Karnataka",
            "country": "India",
            "years_of_experience": 6.0,
            "current_title": "Software Engineer",
            "current_company": "Acme Corp",
            "current_company_size": "201-500",
            "current_industry": "Software",
        },
        "career_history": [
            {
                "company": "Acme Corp",
                "title": "Software Engineer",
                "industry": "Software",
                "start_date": "2021-01-01",
                "end_date": None,
                "is_current": True,
                "duration_months": 66,
                "description": "Worked on backend services.",
            }
        ],
        "education": [{"institution": "Some University", "tier": "tier_3",
                        "degree": "B.Tech", "field": "CS", "start_year": 2014, "end_year": 2018}],
        "skills": [{"name": "Python", "proficiency": "advanced", "duration_months": 60, "endorsements": 10}],
        "redrob_signals": {
            "notice_period_days": 30,
            "willing_to_relocate": True,
            "last_active_date": "2026-06-20",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.6,
            "interview_completion_rate": 0.6,
            "search_appearance_30d": 50,
            "saved_by_recruiters_30d": 2,
            "verified_email": True,
            "verified_phone": True,
            "linkedin_connected": True,
            "skill_assessment_scores": {},
            "expected_salary_range_inr_lpa": {"min": 20, "max": 30},
        },
    }
    for key, value in overrides.items():
        candidate[key] = value
    return candidate


def test_honeypot_clean_profile_not_flagged():
    candidate = _base_candidate()
    assert honeypot_reason(candidate) is None


def test_csv_candidates_parse_and_rank():
    csv_path = Path(__file__).resolve().parent / "sample_candidates.csv"
    csv_path.write_text(
        "candidate_id,title,company,summary,skills,years_of_experience,location,country\n"
        "C1,Senior ML Engineer,Acme,Built retrieval systems with embeddings and hybrid search for production use,Python;Vector Search;Pinecone,6,Bangalore,India\n",
        encoding="utf-8",
    )

    candidates = upload_ranking.load_candidates_from_csv(csv_path)
    assert candidates[0]["profile"]["current_title"] == "Senior ML Engineer"

    ranked = upload_ranking.rank_candidates(candidates, mode="hybrid_scoring")
    assert ranked[0]["candidate_id"] == "C1"
    assert ranked[0]["score"] > 0.35

    csv_path.unlink(missing_ok=True)


def test_honeypot_expert_zero_duration_flagged():
    candidate = _base_candidate()
    candidate["skills"] = [
        {"name": "RAG", "proficiency": "expert", "duration_months": 0, "endorsements": 0},
        {"name": "Pinecone", "proficiency": "expert", "duration_months": 0, "endorsements": 0},
        {"name": "LangChain", "proficiency": "expert", "duration_months": 0, "endorsements": 0},
    ]
    reason = honeypot_reason(candidate)
    assert reason is not None
    assert "expert" in reason


def test_honeypot_date_duration_mismatch_flagged():
    candidate = _base_candidate()
    candidate["career_history"][0]["duration_months"] = 200  # dates imply ~66 months
    reason = honeypot_reason(candidate)
    assert reason is not None


def test_keyword_stuffer_scores_low():
    candidate = _base_candidate()
    candidate["profile"]["current_title"] = "HR Manager"
    candidate["profile"]["current_industry"] = "Consulting"
    candidate["career_history"][0]["title"] = "HR Manager"
    candidate["career_history"][0]["industry"] = "Consulting"
    candidate["career_history"][0]["description"] = "Managed recruiting operations and onboarding."
    candidate["skills"] = [
        {"name": n, "proficiency": "expert", "duration_months": 1, "endorsements": 0}
        for n in ["RAG", "LangChain", "Pinecone", "Vector Search", "Prompt Engineering",
                  "Semantic Search", "LLMs", "Information Retrieval"]
    ]
    feats = features.extract(candidate)
    score, fired = scoring.composite_score(feats)
    assert score < 0.30, f"keyword-stuffer scored too high: {score}"


def test_plain_language_candidate_scores_well():
    candidate = _base_candidate()
    candidate["profile"]["current_title"] = "Senior Machine Learning Engineer"
    candidate["profile"]["current_industry"] = "AI/ML"
    candidate["profile"]["summary"] = (
        "Senior engineer who has spent the last several years building systems "
        "that connect users with relevant information at scale."
    )
    candidate["career_history"][0].update({
        "title": "Senior Machine Learning Engineer",
        "industry": "AI/ML",
        "description": (
            "Built and shipped the ranking system that decides what candidates "
            "recruiters see first, using embeddings and vector representations "
            "to power retrieval at production scale. Owns the evaluation "
            "framework (NDCG, offline-to-online correlation) for the team."
        ),
    })
    candidate["skills"] = [
        {"name": "Vector Representations", "proficiency": "expert", "duration_months": 40, "endorsements": 20},
        {"name": "Information Retrieval Systems", "proficiency": "advanced", "duration_months": 36, "endorsements": 15},
        {"name": "Python", "proficiency": "expert", "duration_months": 70, "endorsements": 30},
    ]
    feats = features.extract(candidate)
    score, fired = scoring.composite_score(feats)
    assert score > 0.45, f"plain-language strong candidate scored too low: {score}"
    assert fired == []


def test_no_visa_path_disqualifier_fires():
    candidate = _base_candidate()
    candidate["profile"]["country"] = "United States"
    candidate["profile"]["location"] = "Austin, USA"
    candidate["redrob_signals"]["willing_to_relocate"] = False
    feats = features.extract(candidate)
    assert feats["no_visa_path"] is True
    score_with, fired = scoring.composite_score(feats)
    assert "no_visa_path" in fired

    candidate["redrob_signals"]["willing_to_relocate"] = True
    feats2 = features.extract(candidate)
    assert feats2["no_visa_path"] is False


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
