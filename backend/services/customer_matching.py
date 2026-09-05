"""
Customer matching service.

Matches extracted customer names against the merchant's existing customer base
using deterministic fuzzy matching (no external AI dependency).

Strategy:
1. Exact phone match (highest confidence)
2. Exact normalized name match
3. Fuzzy name similarity using difflib.SequenceMatcher

Honorifics (ji, bhai, sir, etc.) are stripped before matching.
If confidence is below threshold, returns ambiguous state for merchant confirmation.
"""

import re
from difflib import SequenceMatcher
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models import Customer
from backend.schemas import CustomerMatchCandidate, CustomerMatchResult


# ── Honorific Removal ──────────────────────────────────────────────────────────

HONORIFICS = [
    r"\bji\b", r"\bbhai\b", r"\bsir\b", r"\bmadam\b",
    r"\bdidi\b", r"\baunty\b", r"\buncle\b", r"\bsahab\b",
    r"\bbehan\b", r"\bben\b", r"\bamma\b",
]

HONORIFIC_PATTERN = re.compile(
    "|".join(HONORIFICS), re.IGNORECASE
)


def normalize_name(name: str) -> str:
    """Normalize a customer name for matching.

    - Convert to lowercase
    - Remove honorifics (ji, bhai, sir, madam, etc.)
    - Collapse whitespace
    - Strip leading/trailing whitespace
    """
    normalized = name.lower().strip()
    normalized = HONORIFIC_PATTERN.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


# ── Fuzzy Matching ─────────────────────────────────────────────────────────────

MATCH_THRESHOLD = 0.6  # Below this, customer is considered unmatched
AMBIGUITY_THRESHOLD = 0.8  # Below this but above MATCH_THRESHOLD = ambiguous


def match_customer(
    merchant_id: str,
    extracted_name: str,
    extracted_phone: Optional[str],
    db: Session,
) -> CustomerMatchResult:
    """
    Match an extracted customer reference against the merchant's customer base.

    Returns CustomerMatchResult with:
    - matched_customer: best match (if confident enough)
    - match_score: similarity score
    - match_method: how the match was made
    - is_ambiguous: True if multiple close matches exist
    - is_new_customer: True if no match found
    - candidates: all considered matches
    """
    # Load merchant's customers
    customers = (
        db.query(Customer)
        .filter(Customer.merchant_id == merchant_id)
        .all()
    )

    if not customers:
        return CustomerMatchResult(
            is_new_customer=True,
            match_method="no_customers_exist",
        )

    # Strategy 1: Exact phone match
    if extracted_phone:
        clean_phone = re.sub(r"[^\d+]", "", extracted_phone)
        for c in customers:
            if c.phone and re.sub(r"[^\d+]", "", c.phone) == clean_phone:
                return CustomerMatchResult(
                    matched_customer=CustomerMatchCandidate(
                        id=c.id,
                        name=c.name,
                        phone=c.phone,
                        score=1.0,
                        method="exact_phone",
                    ),
                    match_score=1.0,
                    match_method="exact_phone",
                )

    # Strategy 2: Name matching
    normalized_input = normalize_name(extracted_name)

    if not normalized_input:
        return CustomerMatchResult(
            is_new_customer=True,
            match_method="empty_name",
        )

    candidates: List[CustomerMatchCandidate] = []

    for c in customers:
        normalized_db = normalize_name(c.name)

        # Exact normalized name match
        if normalized_input == normalized_db:
            candidates.append(CustomerMatchCandidate(
                id=c.id,
                name=c.name,
                phone=c.phone,
                score=1.0,
                method="exact_name",
            ))
            continue

        # Fuzzy match
        ratio = SequenceMatcher(None, normalized_input, normalized_db).ratio()

        # Also check if input is a substring of the DB name or vice versa
        if normalized_input in normalized_db or normalized_db in normalized_input:
            ratio = max(ratio, 0.85)

        if ratio >= MATCH_THRESHOLD:
            candidates.append(CustomerMatchCandidate(
                id=c.id,
                name=c.name,
                phone=c.phone,
                score=round(ratio, 3),
                method="fuzzy_name",
            ))

    if not candidates:
        return CustomerMatchResult(
            is_new_customer=True,
            match_method="no_match",
        )

    # Sort by score descending
    candidates.sort(key=lambda x: x.score, reverse=True)

    best = candidates[0]

    # Check for ambiguity: multiple close matches
    is_ambiguous = False
    if len(candidates) > 1:
        second = candidates[1]
        if second.score >= MATCH_THRESHOLD and (best.score - second.score) < 0.15:
            is_ambiguous = True

    # Below ambiguity threshold = needs confirmation
    if best.score < AMBIGUITY_THRESHOLD:
        is_ambiguous = True

    return CustomerMatchResult(
        matched_customer=best,
        match_score=best.score,
        match_method=best.method,
        is_ambiguous=is_ambiguous,
        candidates=candidates[:5],  # Return top 5 candidates
    )
