"""
Deterministic financial validation, idempotency hashing, and security sanitization.

CRITICAL: This module is the guardrail between AI-generated data and the financial ledger.
No AI output should ever reach the database without passing through these validators.

All monetary calculations use decimal.Decimal to avoid floating-point errors.
"""

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from backend.schemas import ValidationResult


# ── Financial Invariant Validation ─────────────────────────────────────────────

def validate_financial_invariant(
    total_amount: Decimal,
    cash_paid: Decimal,
    upi_paid: Decimal,
    credit_amount: Decimal,
) -> ValidationResult:
    """
    Validate the core financial invariant:
        total_amount == cash_paid + upi_paid + credit_amount

    Uses Decimal arithmetic — never floats.

    Returns ValidationResult with:
    - valid: True if invariant holds
    - flag_code: ERR_MATH_MISMATCH if not
    - delta: exact difference
    """
    flags: List[str] = []

    # Check for negative values
    for label, value in [
        ("total_amount", total_amount),
        ("cash_paid", cash_paid),
        ("upi_paid", upi_paid),
        ("credit_amount", credit_amount),
    ]:
        if value < Decimal("0"):
            return ValidationResult(
                valid=False,
                flag_code="ERR_NEGATIVE_AMOUNT",
                delta=abs(value),
                flags=[f"Negative value for {label}: {value}"],
                message=f"{label} cannot be negative.",
            )

    computed_total = cash_paid + upi_paid + credit_amount
    delta = abs(total_amount - computed_total)

    if delta != Decimal("0"):
        return ValidationResult(
            valid=False,
            flag_code="ERR_MATH_MISMATCH",
            delta=delta,
            flags=[
                f"expected={computed_total}, actual_total={total_amount}, delta={delta}"
            ],
            message=f"Financial amounts do not balance. Expected {computed_total}, got {total_amount}. Delta: {delta}",
        )

    return ValidationResult(valid=True, delta=Decimal("0.00"), flags=flags)


# ── VPA Validation ─────────────────────────────────────────────────────────────

VPA_REGEX = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")


def validate_vpa(vpa: str) -> bool:
    """Validate a UPI VPA (Virtual Payment Address) format."""
    return bool(VPA_REGEX.match(vpa))


# ── Idempotency Hashing ───────────────────────────────────────────────────────

def generate_idempotency_hash(
    merchant_id: str,
    transcript: str,
    timestamp: Optional[datetime] = None,
) -> str:
    """
    Generate SHA-256 idempotency hash from:
        merchant_id + normalized_transcript + 15_second_time_bucket

    The same voice note submitted twice within the same 15-second window
    produces the same hash, preventing duplicate financial transactions.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # 15-second time bucket: floor to nearest 15s
    epoch_seconds = int(timestamp.timestamp())
    time_bucket = epoch_seconds - (epoch_seconds % 15)

    # Normalize transcript: lowercase, strip extra whitespace
    normalized = " ".join(transcript.lower().strip().split())

    payload = f"{merchant_id}:{normalized}:{time_bucket}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Prompt Injection Defense ───────────────────────────────────────────────────

# Patterns that should NEVER appear in a legitimate Kirana transaction
INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"ignore\s+(previous|all|system)\s+(instructions?|prompt)", re.IGNORECASE),
    re.compile(r"ignore\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"set\s+credit\s+to\s+zero", re.IGNORECASE),
    re.compile(r"don'?t\s+record\s+this\s+debt", re.IGNORECASE),
    re.compile(r"override\s+validation", re.IGNORECASE),
    re.compile(r"mark\s+(this\s+)?as\s+paid", re.IGNORECASE),
    re.compile(r"bypass\s+(accounting|validation|security)", re.IGNORECASE),
    re.compile(r"delete\s+(all|previous)\s+(entries|records|transactions)", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"update\s+.*\s+set\s+", re.IGNORECASE),
    re.compile(r"alter\s+table", re.IGNORECASE),
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"\{\{.*\}\}", re.IGNORECASE),  # template injection
    re.compile(r"system\s*:\s*", re.IGNORECASE),  # role injection
    re.compile(r"assistant\s*:\s*", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|previous)", re.IGNORECASE),
    re.compile(r"reset\s+(balance|outstanding|udhar|credit)", re.IGNORECASE),
    re.compile(r"make\s+(balance|outstanding|udhar)\s+zero", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
]


def sanitize_transcript(transcript: str) -> Tuple[str, List[str]]:
    """
    Scan a transcript for prompt injection attempts.

    Returns:
        (sanitized_transcript, list_of_flags)

    If injection patterns are detected, the transcript is still returned
    (for auditability) but flags are raised so the transaction is FLAGGED,
    never COMMITTED.
    """
    flags: List[str] = []

    for pattern in INJECTION_PATTERNS:
        if pattern.search(transcript):
            flags.append("ERR_PROMPT_INJECTION")
            break

    # Check for suspicious control characters or encoded sequences
    if any(ord(c) < 32 and c not in ("\n", "\r", "\t") for c in transcript):
        flags.append("ERR_SUSPICIOUS_INSTRUCTION")

    # Check for abnormally long transcripts (likely injected content)
    if len(transcript) > 2000:
        flags.append("ERR_SUSPICIOUS_INSTRUCTION")

    return transcript, flags


# ── Amount Parsing Helpers ─────────────────────────────────────────────────────

def safe_decimal(value) -> Decimal:
    """Safely convert a value to Decimal, defaulting to 0.00 on failure."""
    if value is None:
        return Decimal("0.00")
    try:
        d = Decimal(str(value))
        if d < 0:
            return Decimal("0.00")
        return d.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")
