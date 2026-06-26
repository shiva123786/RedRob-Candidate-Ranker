"""
Structured knowledge extracted by hand from job_description.md (Senior AI Engineer,
Founding Team, Redrob AI). This module is the single place that encodes "what the
JD means" -- every other module consumes these constants rather than re-reading
free text. Keeping it isolated also makes the system easy to defend/re-target:
swap this file for a new JD and the rest of the pipeline (concept matching,
skill credibility, behavioral modifier, honeypot filter) is unchanged.

Each concept group below is a (regex_pattern, weight) used for scanning free text
(headline + summary + career_history descriptions). Patterns are deliberately
phrased around *what a candidate would actually write*, including plain-language
phrasing, not just the buzzword itself -- this is what lets us catch "Tier 5"
candidates who describe the work without naming the tool (see README, "How to
read between the lines").
"""

import re

def _rx(*phrases):
    # NOTE: callers are responsible for passing already-lowercased text.
    # Dropping re.IGNORECASE here is a deliberate performance choice: with
    # ~15 patterns evaluated per candidate across 100K candidates,
    # case-insensitive alternation matching in Python's `re` engine was the
    # single largest cost in the pipeline (profiled at ~15s/5000 candidates,
    # i.e. ~5 minutes for the full pool -- over the compute budget).
    # Lower-casing once per candidate and matching case-sensitively against
    # all-lowercase patterns is functionally identical and dramatically
    # faster.
    return re.compile(r"(?:%s)" % "|".join(phrases))

# ---------------------------------------------------------------------------
# 1. "Things you absolutely need" -- JD section, core must-haves.
#    Each is (compiled_regex, weight). Weight reflects how central the JD says
#    it is. These four buckets are capped independently in scoring.py so a
#    candidate can't max out the whole category by repeating one phrase.
# ---------------------------------------------------------------------------

CORE_CONCEPTS = {
    "embeddings_retrieval": _rx(
        r"sentence[- ]transformers", r"bge\b", r"\be5\b embedding", r"embeddings?\b",
        r"dense retrieval", r"semantic search", r"openai embeddings?",
        r"retrieval[- ]augmented", r"\brag\b", r"nearest[- ]neighb", r"ann index",
        r"embedding drift", r"index refresh",
    ),
    "vector_hybrid_search": _rx(
        r"pinecone", r"weaviate", r"qdrant", r"milvus", r"opensearch",
        r"elasticsearch", r"\bfaiss\b", r"pgvector", r"vector database",
        r"hybrid search", r"hybrid retrieval", r"\bbm25\b", r"vector search",
        r"vector index",
    ),
    "python_production": _rx(
        r"\bpython\b",
    ),
    "eval_frameworks": _rx(
        r"\bndcg\b", r"\bmrr\b", r"\bmap\b(?!s)", r"offline[- ]to[- ]online",
        r"offline.{0,20}online correlation", r"a/?b test", r"evaluation framework",
        r"ranking metric", r"precision@", r"recall@", r"\bp@\d", r"relevance label",
        r"offline benchmark", r"online benchmark",
    ),
}

# Each candidate's score on a core concept is capped at this many "hits" before
# diminishing returns kick in (keyword-stuffing one phrase shouldn't dominate).
CORE_CONCEPT_HIT_CAP = 3

# ---------------------------------------------------------------------------
# 2. Ranking / search / matching systems -- the actual mandate ("own the
#    intelligence layer ... ranking, retrieval, and matching systems").
#    Distinct from the four core buckets because it's about the *system*,
#    not the specific tool -- this is what catches plain-language candidates.
# ---------------------------------------------------------------------------

SYSTEM_MANDATE_CONCEPTS = _rx(
    r"ranking system", r"search system", r"recommendation system",
    r"matching system", r"relevant information at scale",
    r"recruiter[- ]engagement", r"candidate[- ]jd matching", r"query understanding",
    r"search infrastructure", r"search backend", r"search & discovery",
    r"indexing algorithm", r"content matching", r"text encoders?",
    r"vector representations?", r"model adaptation", r"ranking systems?",
    r"decide what (?:to show|recruiters see|candidates see)",
    r"learning[- ]to[- ]rank", r"\bltr\b", r"re-?ranking", r"\bxgboost\b.{0,20}rank",
)

# ---------------------------------------------------------------------------
# 3. Production-deployment language -- distinguishes "shipped to real users"
#    from "built a notebook". JD repeatedly stresses production experience.
# ---------------------------------------------------------------------------

PRODUCTION_LANGUAGE = _rx(
    r"production", r"real users", r"at scale", r"shipped", r"deployed",
    r"live traffic", r"serving traffic", r"in prod\b",
)

# ---------------------------------------------------------------------------
# 4. "Things we'd like but won't reject you for" -- nice-to-haves.
#    Smaller weight, summed with a cap so they can meaningfully help a
#    borderline candidate but never substitute for the core must-haves.
# ---------------------------------------------------------------------------

NICE_TO_HAVE_CONCEPTS = {
    "llm_finetuning": _rx(r"\blora\b", r"\bqlora\b", r"\bpeft\b", r"fine-?tun"),
    "learning_to_rank": _rx(r"learning[- ]to[- ]rank", r"\bltr\b", r"xgboost.{0,20}rank"),
    "hr_recruiting_marketplace": _rx(
        r"hr[- ]?tech", r"recruit(?:ing|er)", r"talent (?:intelligence|platform)",
        r"job (?:marketplace|platform)", r"marketplace product",
    ),
    "distributed_systems": _rx(
        r"distributed systems?", r"large[- ]scale inference", r"inference optimi[sz]ation",
        r"low[- ]latency serving", r"horizontal scal",
    ),
    "open_source_validation": _rx(
        r"open[- ]source", r"published a paper", r"\bpaper\b.{0,15}(?:accepted|published)",
        r"conference talk", r"gave a talk", r"\bblog post", r"github\.com",
    ),
}

# ---------------------------------------------------------------------------
# 5. "Things we explicitly do NOT want" -- disqualifying / down-weighting
#    patterns. These are multiplicative penalties applied in scoring.py, not
#    hard excludes (per challenge framing: "down-weight appropriately", with
#    the sole hard exclude being the honeypot filter in honeypot.py).
# ---------------------------------------------------------------------------

# 5a. Pure-services-firm career (explicitly named in the JD). A candidate
# currently at one of these but with *prior* product-company history is fine
# -- only an entire career confined to this set is penalized.
SERVICES_FIRMS = {"TCS", "Infosys", "Wipro", "Accenture", "Cognizant", "Capgemini"}

# 5b. CV / speech / robotics specialization without NLP/IR crossover.
CV_SPEECH_ROBOTICS_TERMS = _rx(
    r"computer vision", r"\byolo\b", r"object detection", r"image classification",
    r"\bcnn\b", r"\bgan\b", r"diffusion model", r"\bopencv\b", r"speech recognition",
    r"\btts\b", r"\basr\b", r"robotics", r"slam\b", r"autonomous (?:vehicle|robot)",
)
NLP_IR_CROSSOVER_TERMS = _rx(
    r"\bnlp\b", r"natural language", r"information retrieval", r"\bllm", r"\brag\b",
    r"embeddings?", r"semantic search", r"text encoders?", r"ranking system",
    r"search system", r"language model",
)

# 5c. Stale-architect: senior title that signals "moved into architecture/lead
# and stopped writing code" combined with no coding language in the current
# role's description.
STALE_TITLE_TERMS = _rx(
    r"\barchitect\b", r"\btech(?:nical)? lead\b", r"engineering manager",
    r"\bdirector\b", r"\bhead of\b", r"\bvp\b",
)
CODING_LANGUAGE = _rx(
    r"\bimplement", r"\bbuilt\b", r"\bwrote\b", r"\bshipped\b", r"\bcoded\b",
    r"\bdesigned and built\b", r"\brefactor", r"\bdebugg", r"\bcommit",
)

# 5d. Title-chaser: rapid title escalation through short stints.
TITLE_RANK = {
    "intern": 0, "junior": 1, "associate": 1, "engineer": 2, "senior": 3,
    "staff": 4, "lead": 4, "principal": 5, "director": 6, "head": 6, "vp": 7,
}

# 5e. Recent-LangChain-wrapper-only: AI experience confined to the last 12
# months and built only around LangChain/OpenAI calls, with no pre-LLM-era
# production ML history.
WRAPPER_ONLY_TERMS = _rx(r"langchain", r"openai api", r"gpt-?\d", r"prompt engineering")
PRE_LLM_ML_TERMS = _rx(
    r"scikit-?learn", r"\bxgboost\b", r"\bpytorch\b", r"\btensorflow\b",
    r"feature engineering", r"statistical modeling", r"machine learning",
    r"deep learning", r"recommendation system", r"search system", r"ranking system",
)

# ---------------------------------------------------------------------------
# 6. Location preferences (JD: "On location, comp, and logistics").
# ---------------------------------------------------------------------------

PRIMARY_HUBS = {"pune", "noida"}
WELCOME_HUBS = {"hyderabad", "mumbai", "delhi", "gurgaon", "gurugram", "faridabad",
                "ghaziabad", "new delhi"}

# ---------------------------------------------------------------------------
# 7. "Ideal candidate" experience band (soft, not a hard filter).
# ---------------------------------------------------------------------------

IDEAL_EXPERIENCE_MIN = 5
IDEAL_EXPERIENCE_MAX = 9
IDEAL_EXPERIENCE_SOFT_MIN = 4.0   # below this, fit decays faster (JD: 4yrs can be enough)
IDEAL_EXPERIENCE_SOFT_MAX = 15.0  # JD: some people never hit it after 15 -- not a wall,
                                   # but the JD's center of gravity is 5-9

# Notice period scoring tiers (JD: "love sub-30-day", "can buy out up to 30",
# "30+ day ... still in scope but bar gets higher").
NOTICE_PERIOD_GREAT = 30
NOTICE_PERIOD_OK = 60

# ---------------------------------------------------------------------------
# 8. Industry classification, derived directly from the candidate_schema's
#    `current_industry` / career_history[].industry field rather than from
#    company-name lists. This generalizes better than hardcoding company
#    names (which would overfit to the specific fictional/real companies
#    that happen to appear in this dataset) and is exactly the kind of
#    structured signal a recruiting platform would actually have.
# ---------------------------------------------------------------------------

PRODUCT_TECH_INDUSTRIES = {
    "AI/ML", "SaaS", "Software", "Fintech", "EdTech", "E-commerce",
    "Food Delivery", "AdTech", "Insurance Tech",
}
SERVICES_OR_NOISE_INDUSTRIES = {
    "IT Services", "Consulting", "Manufacturing", "Conglomerate",
    "Paper Products", "Transportation",
}

# Academic / research-only language (JD: "academic labs, research-only roles
# without any production deployment"). Distinct from PRODUCTION_LANGUAGE above.
ACADEMIC_ONLY_TERMS = _rx(
    r"\bpostdoc", r"\bphd thesis\b", r"academic lab", r"\bprofessor\b",
    r"research[- ]only", r"no production", r"never (?:shipped|deployed)",
)

