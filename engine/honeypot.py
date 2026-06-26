"""
Honeypot detection.

The challenge dataset embeds ~80 candidates with "subtly impossible profiles"
(redrob_signals_doc.md, Section 7) and disqualifies any submission whose top
100 contains more than 10% honeypots. These are forced to relevance tier 0 in
the hidden ground truth, so the only correct move is to find and hard-exclude
them -- no amount of skill/title match should let one back in.

We identified the dataset's actual honeypot signature empirically (see the
exploratory notes in README.md, "How honeypots were found") rather than
guessing from the doc's prose alone:

  1. `expert`-proficiency skill claimed with ~0 months of use. On the real
     population this NEVER happens even once (99,979/100,000 candidates have
     zero such skills); the ~21 candidates that do have it have 3-5 of them
     simultaneously. Clean bimodal separation -> any occurrence is a flag.

  2. career_history `duration_months` inconsistent with the entry's own
     `start_date`/`end_date` by more than 3 months. Again clean separation:
     99,965/100,000 candidates have differences of <=3 months (ordinary
     rounding); the honeypot tail jumps straight to 9-150+ months of
     inconsistency.

  3. Sum of career_history `duration_months` exceeding the stated
     `years_of_experience` by more than 24 months. Same clean separation
     pattern (99,977 vs a tail starting at 25+ months over).

Each heuristic alone has zero false positives against the bulk distribution
(verified by inspecting the bimodal histograms), so we flag on ANY of the
three rather than requiring all three -- maximizing recall on the honeypot
set without spending the submission's honeypot budget on legitimate
candidates.
"""

from datetime import date

TODAY = date(2026, 6, 26)

EXPERT_ZERO_DURATION_THRESHOLD_MONTHS = 1
DATE_DURATION_MISMATCH_THRESHOLD_MONTHS = 3
YOE_CAREER_TOTAL_MISMATCH_THRESHOLD_MONTHS = 24


def _parse_date(s):
    if not s:
        return TODAY
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except ValueError:
        return TODAY


def _months_between(start_s, end_s):
    start = _parse_date(start_s)
    end = _parse_date(end_s) if end_s else TODAY
    return (end.year - start.year) * 12 + (end.month - start.month)


def honeypot_reason(candidate):
    """Return a short string naming why a candidate was flagged, or None."""
    skills = candidate.get("skills", [])
    expert_zero = sum(
        1 for s in skills
        if s.get("proficiency") == "expert"
        and s.get("duration_months", 999) <= EXPERT_ZERO_DURATION_THRESHOLD_MONTHS
    )
    if expert_zero >= 1:
        return f"{expert_zero} skill(s) marked 'expert' with ~0 months of use"

    for c in candidate.get("career_history", []):
        computed = _months_between(c["start_date"], c.get("end_date"))
        stated = c.get("duration_months", computed)
        if abs(computed - stated) > DATE_DURATION_MISMATCH_THRESHOLD_MONTHS:
            return (
                f"career entry at {c.get('company','?')} claims "
                f"{stated} months but dates imply {computed}"
            )

    total_career_months = sum(c.get("duration_months", 0) for c in candidate.get("career_history", []))
    yoe_months = candidate.get("profile", {}).get("years_of_experience", 0) * 12
    if total_career_months - yoe_months > YOE_CAREER_TOTAL_MISMATCH_THRESHOLD_MONTHS:
        return (
            f"career_history totals {total_career_months:.0f} months but "
            f"years_of_experience implies {yoe_months:.0f}"
        )

    return None


def is_honeypot(candidate):
    return honeypot_reason(candidate) is not None
