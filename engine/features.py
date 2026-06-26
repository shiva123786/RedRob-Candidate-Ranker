"""
Per-candidate feature extraction.

Pulls every signal the scorer needs out of one candidate JSON record. Kept
deliberately free of any "is this good or bad" judgment -- that's
scoring.py's job. This separation is what makes the reasoning strings
trustworthy: scoring.py only ever talks about facts that were actually
extracted here, never something inferred-and-forgotten.
"""

from datetime import date

from . import jd_knowledge as K

TODAY = date(2026, 6, 26)


def _full_text(candidate):
    profile = candidate["profile"]
    parts = [profile.get("headline", ""), profile.get("summary", "")]
    for role in candidate.get("career_history", []):
        parts.append(role.get("description", ""))
    parts.extend(s["name"] for s in candidate.get("skills", []))
    return " \n ".join(parts)


def _capped_hits(pattern, text, cap):
    hits = len(pattern.findall(text))
    return min(hits, cap)


def _seniority_rank(title):
    tl = title.lower()
    best = 2  # default "engineer"-level if no keyword matches
    for kw, rank in K.TITLE_RANK.items():
        if kw in tl:
            best = max(best, rank)
    return best


def _skill_proficiency_score(prof):
    return {"beginner": 0.3, "intermediate": 0.55, "advanced": 0.8, "expert": 1.0}.get(prof, 0.4)


def _skill_relevance_weight(name):
    nl = name.lower()
    core_tools = {
        "sentence transformers", "bge", "e5", "embeddings", "pinecone", "weaviate",
        "qdrant", "milvus", "opensearch", "elasticsearch", "faiss", "pgvector",
        "bm25", "python", "vector search",
    }
    rare_mandate_phrases = {
        "information retrieval systems", "search backend", "text encoders",
        "vector representations", "content matching", "model adaptation",
        "ranking systems", "search & discovery", "workflow orchestration",
        "search infrastructure", "indexing algorithms", "open-source ml libraries",
        "natural language processing", "document processing",
    }
    ai_buzzword_cluster = {
        "hugging face transformers", "langchain", "information retrieval", "llms",
        "recommendation systems", "semantic search", "sentence transformers",
        "prompt engineering", "rag", "fine-tuning llms",
    }
    nice_to_have = {
        "qlora", "learning to rank", "tensorflow", "pytorch", "peft", "lora",
        "nlp", "machine learning", "deep learning", "haystack", "llamaindex",
        "scikit-learn",
    }
    cv_speech = {
        "yolo", "gans", "opencv", "asr", "image classification", "computer vision",
        "speech recognition", "cnn", "diffusion models", "tts", "object detection",
    }
    if nl in rare_mandate_phrases:
        return 1.0
    if nl in core_tools:
        return 1.0
    if nl in nice_to_have:
        return 0.7
    if nl in ai_buzzword_cluster:
        return 0.55
    if nl in cv_speech:
        return -0.3
    return 0.0


def _skill_credibility(candidate):
    """Sum of relevance_weight * proficiency * trust, where trust discounts
    claims unsupported by duration/endorsements/assessment scores. This is
    the layer that separates a "real" skill from a keyword-stuffed one."""
    assessments = candidate.get("redrob_signals", {}).get("skill_assessment_scores", {})
    total = 0.0
    cv_speech_hits = 0
    for s in candidate.get("skills", []):
        weight = _skill_relevance_weight(s["name"])
        if weight == 0.0:
            continue
        if weight < 0:
            cv_speech_hits += 1
        prof_score = _skill_proficiency_score(s.get("proficiency", "beginner"))
        duration = s.get("duration_months", 0)
        endorsements = s.get("endorsements", 0)
        # Duration trust: a claimed skill with little time behind it is
        # discounted, regardless of proficiency level.
        duration_trust = min(1.0, 0.25 + duration / 24.0)
        endorsement_trust = min(1.0, 0.5 + endorsements / 40.0)
        trust = 0.5 * duration_trust + 0.5 * endorsement_trust
        if s["name"] in assessments:
            assessed = assessments[s["name"]]
            trust *= 0.4 + assessed / 100.0 * 0.8  # 0 -> 0.4x, 100 -> 1.2x
        total += weight * prof_score * trust
    return total, cv_speech_hits


def _location_fit(profile, signals):
    loc = profile.get("location", "").lower()
    country = profile.get("country", "")
    if country != "India":
        return 0.15 if signals.get("willing_to_relocate") else -0.5
    if any(hub in loc for hub in K.PRIMARY_HUBS):
        return 1.0
    if any(hub in loc for hub in K.WELCOME_HUBS):
        return 0.75
    return 0.55 if signals.get("willing_to_relocate") else 0.3


def _notice_period_fit(days):
    if days <= K.NOTICE_PERIOD_GREAT:
        return 1.0
    if days <= K.NOTICE_PERIOD_OK:
        return 0.6
    if days <= 90:
        return 0.3
    return 0.1


def _experience_fit(yoe):
    if K.IDEAL_EXPERIENCE_MIN <= yoe <= K.IDEAL_EXPERIENCE_MAX:
        return 1.0
    if yoe < K.IDEAL_EXPERIENCE_MIN:
        if yoe < K.IDEAL_EXPERIENCE_SOFT_MIN:
            return max(0.0, 0.55 - (K.IDEAL_EXPERIENCE_SOFT_MIN - yoe) * 0.15)
        return 0.7 + 0.3 * (yoe - K.IDEAL_EXPERIENCE_SOFT_MIN) / (K.IDEAL_EXPERIENCE_MIN - K.IDEAL_EXPERIENCE_SOFT_MIN)
    over = yoe - K.IDEAL_EXPERIENCE_MAX
    return max(0.25, 1.0 - over * 0.05)


def _education_fit(education):
    tiers = {"tier_1": 1.0, "tier_2": 0.75, "tier_3": 0.5, "tier_4": 0.4, "unknown": 0.45}
    if not education:
        return 0.45
    return max(tiers.get(e.get("tier", "unknown"), 0.45) for e in education)


def _industry_quality(career_history):
    total_months = sum(c.get("duration_months", 0) for c in career_history) or 1
    product_months = sum(
        c.get("duration_months", 0) for c in career_history
        if c.get("industry") in K.PRODUCT_TECH_INDUSTRIES
    )
    return product_months / total_months


def _services_only(career_history):
    companies = {c["company"] for c in career_history}
    return bool(companies) and companies.issubset(K.SERVICES_FIRMS)


def _stale_architect(candidate):
    profile = candidate["profile"]
    title = profile.get("current_title", "")
    if not K.STALE_TITLE_TERMS.search(title.lower()):
        return False
    current_roles = [c for c in candidate["career_history"] if c.get("is_current")]
    if not current_roles:
        return False
    role = current_roles[0]
    if role.get("duration_months", 0) < 18:
        return False
    return not K.CODING_LANGUAGE.search(role.get("description", "").lower())


def _wrapper_only(candidate, text):
    yoe = candidate["profile"]["years_of_experience"]
    has_wrapper = bool(K.WRAPPER_ONLY_TERMS.search(text))
    has_pre_llm = bool(K.PRE_LLM_ML_TERMS.search(text))
    if yoe < 1.5 and has_wrapper and not has_pre_llm:
        return True
    most_recent = max(candidate["career_history"], key=lambda c: c.get("start_date", ""))
    if most_recent.get("duration_months", 999) <= 12 and has_wrapper and not has_pre_llm:
        # AI exposure confined to the most recent (<=12mo) role only
        older_text = " ".join(
            c.get("description", "") for c in candidate["career_history"] if c is not most_recent
        ).lower()
        if not K.PRE_LLM_ML_TERMS.search(older_text):
            return True
    return False


def _title_chaser(career_history):
    if len(career_history) < 3:
        return False
    sorted_roles = sorted(career_history, key=lambda c: c.get("start_date", ""))
    short_stints = sum(1 for c in sorted_roles if c.get("duration_months", 999) <= 18)
    ranks = [_seniority_rank(c["title"]) for c in sorted_roles]
    escalating = all(b >= a for a, b in zip(ranks, ranks[1:])) and ranks[-1] > ranks[0]
    return short_stints >= 3 and escalating and len(sorted_roles) >= 3


def _behavioral_modifier(signals):
    """Multiplicative availability modifier in roughly [0.45, 1.15]. A
    perfect-on-paper candidate who is dark/unresponsive should not outrank a
    slightly-weaker but actually-reachable candidate; this is the lever that
    enforces that."""
    last_active = signals.get("last_active_date")
    days_inactive = 9999
    if last_active:
        y, m, d = map(int, last_active.split("-"))
        days_inactive = (TODAY - date(y, m, d)).days

    if days_inactive <= 14:
        recency = 1.0
    elif days_inactive <= 30:
        recency = 0.92
    elif days_inactive <= 90:
        recency = 0.75
    elif days_inactive <= 180:
        recency = 0.55
    else:
        recency = 0.4

    response_rate = signals.get("recruiter_response_rate", 0.0)
    response_term = 0.6 + 0.5 * response_rate  # 0 -> 0.6, 1 -> 1.1

    open_to_work = 1.05 if signals.get("open_to_work_flag") else 0.9

    interview_rate = signals.get("interview_completion_rate", 0.5)
    interview_term = 0.85 + 0.2 * interview_rate

    engagement_proxy = min(1.0, (signals.get("search_appearance_30d", 0) / 200.0))
    saved_proxy = min(1.0, signals.get("saved_by_recruiters_30d", 0) / 10.0)
    visibility_term = 0.9 + 0.1 * max(engagement_proxy, saved_proxy)

    verification_term = 1.0
    verification_term += 0.02 if signals.get("verified_email") else 0
    verification_term += 0.02 if signals.get("verified_phone") else 0
    verification_term += 0.01 if signals.get("linkedin_connected") else 0

    modifier = recency * response_term * open_to_work * interview_term * visibility_term * verification_term
    return max(0.4, min(1.2, modifier))


def extract(candidate):
    profile = candidate["profile"]
    signals = candidate.get("redrob_signals", {})
    career_history = candidate["career_history"]
    text = _full_text(candidate).lower()

    core_concepts = {
        name: _capped_hits(pattern, text, K.CORE_CONCEPT_HIT_CAP)
        for name, pattern in K.CORE_CONCEPTS.items()
    }
    nice_to_have = {
        name: _capped_hits(pattern, text, 2)
        for name, pattern in K.NICE_TO_HAVE_CONCEPTS.items()
    }
    system_mandate_hits = _capped_hits(K.SYSTEM_MANDATE_CONCEPTS, text, 4)
    production_hits = _capped_hits(K.PRODUCTION_LANGUAGE, text, 3)

    skill_credibility, cv_speech_skill_hits = _skill_credibility(candidate)
    # CV/speech dominance is judged from the *structured* skill list (not a
    # second free-text scan, which would double-count the same evidence
    # since skill names are also folded into `text`) against clear NLP/IR
    # system evidence (retrieval/vector-search concepts + the JD's own
    # ranking/search/matching mandate language). Require both >=3 CV/speech
    # skills *and* zero NLP/IR system evidence so a strong NLP candidate who
    # also lists one or two incidental CV skills (common in this dataset's
    # randomly-bundled skill lists) is never penalized.
    nlp_ir_system_evidence = (
        system_mandate_hits
        + core_concepts["embeddings_retrieval"]
        + core_concepts["vector_hybrid_search"]
    )
    cv_speech_dominant = cv_speech_skill_hits >= 3 and nlp_ir_system_evidence == 0

    academic_only = bool(K.ACADEMIC_ONLY_TERMS.search(text)) and production_hits == 0

    return {
        "candidate_id": candidate["candidate_id"],
        "anonymized_name": profile.get("anonymized_name", ""),
        "years_of_experience": profile["years_of_experience"],
        "current_title": profile["current_title"],
        "current_company": profile["current_company"],
        "location": profile["location"],
        "country": profile["country"],
        "core_concepts": core_concepts,
        "nice_to_have": nice_to_have,
        "system_mandate_hits": system_mandate_hits,
        "production_hits": production_hits,
        "skill_credibility": skill_credibility,
        "cv_speech_dominant": cv_speech_dominant,
        "title_seniority": _seniority_rank(profile["current_title"]),
        "experience_fit": _experience_fit(profile["years_of_experience"]),
        "location_fit": _location_fit(profile, signals),
        "notice_period_fit": _notice_period_fit(signals.get("notice_period_days", 60)),
        "education_fit": _education_fit(candidate.get("education", [])),
        "industry_quality": _industry_quality(career_history),
        "services_only": _services_only(career_history),
        "stale_architect": _stale_architect(candidate),
        "wrapper_only": _wrapper_only(candidate, text),
        "title_chaser": _title_chaser(career_history),
        "academic_only": academic_only,
        "no_visa_path": profile.get("country") != "India" and not signals.get("willing_to_relocate"),
        "behavioral_modifier": _behavioral_modifier(signals),
        "notice_period_days": signals.get("notice_period_days"),
        "willing_to_relocate": signals.get("willing_to_relocate"),
        "last_active_date": signals.get("last_active_date"),
        "recruiter_response_rate": signals.get("recruiter_response_rate"),
        "open_to_work_flag": signals.get("open_to_work_flag"),
    }
