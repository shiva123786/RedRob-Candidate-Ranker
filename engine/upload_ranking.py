import csv
import json
from pathlib import Path

from . import features, scoring
from .honeypot import honeypot_reason


def _normalize_candidate(candidate_id, row):
    title = (row.get("title") or row.get("current_title") or "").strip()
    company = (row.get("company") or row.get("current_company") or "").strip()
    summary = (row.get("summary") or row.get("profile_summary") or "").strip()
    skills = [s.strip() for s in (row.get("skills") or "").split(";") if s.strip()]
    years = float(row.get("years_of_experience", 0) or 0)
    location = (row.get("location") or "").strip()
    country = (row.get("country") or "India").strip()

    profile = {
        "anonymized_name": row.get("name") or row.get("anonymized_name") or f"Candidate {candidate_id}",
        "headline": title,
        "summary": summary,
        "location": location,
        "country": country,
        "years_of_experience": years,
        "current_title": title,
        "current_company": company,
        "current_company_size": row.get("company_size") or "",
        "current_industry": row.get("industry") or "",
    }

    career_history = []
    if title or company:
        career_history.append({
            "company": company,
            "title": title,
            "industry": row.get("industry") or "",
            "start_date": row.get("start_date") or "2020-01-01",
            "end_date": row.get("end_date") or None,
            "is_current": True,
            "duration_months": int(row.get("duration_months") or 0) or max(24, int(years * 12) if years else 24),
            "description": summary,
        })

    return {
        "candidate_id": candidate_id,
        "profile": profile,
        "career_history": career_history,
        "education": [],
        "skills": [
            {
                "name": skill,
                "proficiency": row.get("proficiency") or "intermediate",
                "duration_months": int(row.get("skill_duration_months") or 0) or 6,
                "endorsements": int(row.get("endorsements") or 0) or 0,
            }
            for skill in skills
        ],
        "redrob_signals": {
            "notice_period_days": int(row.get("notice_period_days") or 0) or 30,
            "willing_to_relocate": str(row.get("willing_to_relocate", "true")).lower() in {"1", "true", "yes", "y"},
            "last_active_date": row.get("last_active_date") or "2026-06-20",
            "open_to_work_flag": str(row.get("open_to_work_flag", "true")).lower() in {"1", "true", "yes", "y"},
            "recruiter_response_rate": float(row.get("recruiter_response_rate") or 0.5),
            "interview_completion_rate": float(row.get("interview_completion_rate") or 0.5),
            "search_appearance_30d": int(row.get("search_appearance_30d") or 0),
            "saved_by_recruiters_30d": int(row.get("saved_by_recruiters_30d") or 0),
            "verified_email": str(row.get("verified_email", "true")).lower() in {"1", "true", "yes", "y"},
            "verified_phone": str(row.get("verified_phone", "true")).lower() in {"1", "true", "yes", "y"},
            "linkedin_connected": str(row.get("linkedin_connected", "true")).lower() in {"1", "true", "yes", "y"},
            "skill_assessment_scores": {},
            "expected_salary_range_inr_lpa": {"min": 20, "max": 30},
        },
    }


def load_candidates_from_csv(path):
    path = Path(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [_normalize_candidate(row.get("candidate_id") or f"CSV_{idx:04d}", row) for idx, row in enumerate(rows)]


def _mode_boost(mode, text):
    if mode == "lexical":
        return 0.0
    phrases = {
        "semantic_search": ["semantic", "retrieval", "matching", "relevant information"],
        "vector_embeddings": ["embeddings", "vector", "hybrid search", "retrieval"],
        "llm_ranking": ["llm", "ranking", "re-ranking", "evaluation"],
        "hybrid_scoring": ["embeddings", "retrieval", "hybrid search", "vector search", "ranking system", "production"],
    }
    boost = 0.0
    for phrase in phrases.get(mode, []):
        if phrase in text:
            boost += 0.04
    return min(0.2, boost)


def rank_candidates(candidates, mode="lexical"):
    ranked = []
    for candidate in candidates:
        feats = features.extract(candidate)
        score, fired = scoring.composite_score(feats)
        text = " ".join([
            candidate["profile"].get("summary", ""),
            candidate["profile"].get("headline", ""),
            *[c.get("description", "") for c in candidate.get("career_history", [])],
        ]).lower()
        score = min(1.0, score + _mode_boost(mode, text))
        ranked.append({
            "candidate_id": candidate["candidate_id"],
            "score": round(score, 4),
            "reasoning": scoring.generate_reasoning(feats, fired),
            "feats": feats,
            "fired_disqualifiers": fired,
        })
    ranked.sort(key=lambda item: (-item["score"], item["candidate_id"]))
    return ranked


def export_ranked_results(ranked, out_path):
    out_path = Path(out_path)
    rows = []
    for index, item in enumerate(ranked, start=1):
        feats = item["feats"]
        rows.append({
            "rank": index,
            "candidate_id": item["candidate_id"],
            "anonymized_name": feats["anonymized_name"],
            "score": item["score"],
            "reasoning": item["reasoning"],
            "current_title": feats["current_title"],
            "current_company": feats["current_company"],
            "years_of_experience": feats["years_of_experience"],
            "location": feats["location"],
            "country": feats["country"],
            "matched_concepts": [k.replace("_", " ") for k, v in feats["core_concepts"].items() if v > 0],
            "nice_to_have_matched": [k.replace("_", " ") for k, v in feats["nice_to_have"].items() if v > 0],
            "fired_disqualifiers": item["fired_disqualifiers"],
            "behavioral_modifier": round(feats["behavioral_modifier"], 3),
            "notice_period_days": feats["notice_period_days"],
            "willing_to_relocate": feats["willing_to_relocate"],
            "open_to_work_flag": feats["open_to_work_flag"],
        })
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2)
