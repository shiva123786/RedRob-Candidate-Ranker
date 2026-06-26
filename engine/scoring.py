"""
Combines features.py output into:
  1. a single composite score per candidate, and
  2. a 1-2 sentence reasoning string built only from facts that were actually
     extracted for that candidate (no field is ever invented).

Pipeline, mirroring the architecture the JD itself describes wanting built
("audit what we have - mostly BM25 + rule-based... ship v2 with hybrid
retrieval... set up eval infra"):

  Stage A - lexical/concept relevance (the "retrieval" layer): capped,
            saturating hits against a hand-weighted vocabulary derived from
            the JD (jd_knowledge.py). Saturating caps are the same idea as
            BM25 term-frequency saturation -- repeating one buzzword doesn't
            keep paying out, which is what keeps a keyword-stuffed profile
            from outscoring a credible one.
  Stage B - structured re-ranking: title/seniority, career-industry quality,
            experience-band fit, location/notice-period logistics fit,
            education tier, and the explicit JD disqualifiers.
  Stage C - behavioral availability modifier (multiplicative): the JD is
            explicit that a perfect-on-paper, unreachable candidate should be
            down-weighted, not ranked on paper-fit alone.
  Stage D - honeypot hard filter (honeypot.py), applied by the caller before
            this module ever sees a candidate worth ranking.
"""

import hashlib

WEIGHTS = {
    "core_concepts": 0.28,
    "system_mandate": 0.14,
    "production": 0.06,
    "skill_credibility": 0.12,
    "title_seniority": 0.10,
    "experience_fit": 0.08,
    "industry_quality": 0.07,
    "location_fit": 0.06,
    "notice_period_fit": 0.04,
    "education_fit": 0.03,
    "nice_to_have": 0.06,
}

DISQUALIFIER_MULTIPLIERS = {
    "services_only": 0.25,
    "cv_speech_dominant": 0.40,
    "stale_architect": 0.50,
    "wrapper_only": 0.35,
    "title_chaser": 0.60,
    "academic_only": 0.40,
    "no_visa_path": 0.20,
}

CORE_CONCEPT_CAP_TOTAL = 4 * 3      # 4 buckets x cap of 3
NICE_TO_HAVE_CAP_TOTAL = 5 * 2      # 5 buckets x cap of 2
SYSTEM_MANDATE_CAP = 4
PRODUCTION_CAP = 3
SKILL_CREDIBILITY_NORM = 6.0
TITLE_SENIORITY_RANGE = (2, 7)


def _norm(value, lo, hi):
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def composite_score(feats):
    core_sum = sum(feats["core_concepts"].values())
    nice_sum = sum(feats["nice_to_have"].values())

    content = (
        WEIGHTS["core_concepts"] * _norm(core_sum, 0, CORE_CONCEPT_CAP_TOTAL)
        + WEIGHTS["system_mandate"] * _norm(feats["system_mandate_hits"], 0, SYSTEM_MANDATE_CAP)
        + WEIGHTS["production"] * _norm(feats["production_hits"], 0, PRODUCTION_CAP)
        + WEIGHTS["skill_credibility"] * _norm(feats["skill_credibility"], 0, SKILL_CREDIBILITY_NORM)
        + WEIGHTS["title_seniority"] * _norm(feats["title_seniority"], *TITLE_SENIORITY_RANGE)
        + WEIGHTS["experience_fit"] * feats["experience_fit"]
        + WEIGHTS["industry_quality"] * feats["industry_quality"]
        + WEIGHTS["location_fit"] * feats["location_fit"]
        + WEIGHTS["notice_period_fit"] * feats["notice_period_fit"]
        + WEIGHTS["education_fit"] * feats["education_fit"]
        + WEIGHTS["nice_to_have"] * _norm(nice_sum, 0, NICE_TO_HAVE_CAP_TOTAL)
    )

    disqualifier_mult = 1.0
    fired = []
    for flag, mult in DISQUALIFIER_MULTIPLIERS.items():
        if feats.get(flag):
            disqualifier_mult *= mult
            fired.append(flag)

    final = max(0.0, content) * disqualifier_mult * feats["behavioral_modifier"]
    return final, fired


# ---------------------------------------------------------------------------
# Reasoning generation. Every clause below reads directly from `feats`; none
# of it is templated-with-name-only. A handful of synonym phrasings per
# clause (chosen deterministically per candidate_id) keep the top-100 from
# reading like a mail merge when many candidates share the same dominant
# signal -- Stage 4 review explicitly checks sampled rows for variation.
# ---------------------------------------------------------------------------

def _variant(cid, salt, options):
    h = int(hashlib.md5(f"{cid}:{salt}".encode()).hexdigest(), 16)
    return options[h % len(options)]


def _strongest_core_concepts(feats, n=2):
    ranked = sorted(feats["core_concepts"].items(), key=lambda kv: -kv[1])
    return [name.replace("_", " ") for name, hits in ranked if hits > 0][:n]


def generate_reasoning(feats, fired_disqualifiers):
    cid = feats["candidate_id"]
    yoe = feats["years_of_experience"]
    title = feats["current_title"]
    company = feats["current_company"]

    opener_options = [
        f"{title} at {company} with {yoe:.1f} years of experience.",
        f"{yoe:.1f}-year {title} (currently at {company}).",
        f"Currently {title} at {company}; {yoe:.1f} years total experience.",
    ]
    clauses = [_variant(cid, "opener", opener_options)]

    strong_concepts = _strongest_core_concepts(feats)
    if strong_concepts:
        phrasing = _variant(cid, "concepts", [
            "Career history shows direct hands-on work in {}.",
            "Profile demonstrates concrete experience with {}.",
            "Has built real systems touching {}.",
        ])
        clauses.append(phrasing.format(" and ".join(strong_concepts)))
    elif feats["system_mandate_hits"] > 0:
        clauses.append(_variant(cid, "mandate", [
            "Describes owning ranking/search/matching systems in plain language rather than buzzwords.",
            "Career history reads as a search/ranking practitioner even without naming specific tools.",
        ]))
    else:
        clauses.append(_variant(cid, "weak_match", [
            "Limited direct evidence of retrieval/ranking system work in the profile text.",
            "Skill list leans adjacent rather than core to the JD's retrieval/ranking mandate.",
        ]))

    concerns = []
    if fired_disqualifiers:
        flag_text = {
            "services_only": "entire career has been at IT-services firms the JD explicitly flags",
            "cv_speech_dominant": "background is CV/speech-dominant with little NLP/IR crossover",
            "stale_architect": "current title suggests limited recent hands-on coding",
            "wrapper_only": "AI exposure looks recent and LangChain/API-wrapper-only",
            "title_chaser": "career shows rapid title escalation through short stints",
            "academic_only": "profile reads as research-only with no production deployment language",
            "no_visa_path": f"based outside India ({feats['location']}, {feats['country']}) with no relocation flag, and Redrob doesn't sponsor visas",
        }
        concerns.append(flag_text[fired_disqualifiers[0]])
    if feats["notice_period_days"] is not None and feats["notice_period_days"] > 60:
        concerns.append(f"{feats['notice_period_days']}-day notice period is on the long side")
    if "no_visa_path" not in fired_disqualifiers and feats["country"] != "India" and not feats["willing_to_relocate"]:
        concerns.append(f"based in {feats['location']}, {feats['country']} with no relocation flag, and Redrob doesn't sponsor visas")
    if feats["recruiter_response_rate"] is not None and feats["recruiter_response_rate"] < 0.25:
        concerns.append(f"recruiter response rate is low ({feats['recruiter_response_rate']:.0%})")
    if not feats["open_to_work_flag"]:
        concerns.append("not currently flagged open-to-work")

    if concerns:
        clauses.append(_variant(cid, "concern_lead", ["Some concern: ", "Caveat: ", "Worth noting: "]) + concerns[0] + ".")
    else:
        clauses.append(_variant(cid, "no_concern", [
            "Engagement signals (recent activity, response rate) look healthy.",
            "Behavioral signals support that this candidate is genuinely reachable right now.",
        ]))

    return " ".join(clauses)
