"""
Structured extraction from Hinglish voice transcripts.

Supports:
- MockExtractionProvider: deterministic regex-based parser (no AI needed)
- OpenAIExtractionProvider: OpenAI structured JSON extraction
- GroqExtractionProvider: Groq-compatible structured extraction

The mock provider handles all demo sentences correctly using pattern matching
and Hinglish financial vocabulary normalization.

KEY IMPROVEMENT: Hindi word-form numbers (dedh sau, dhai hazaar, paanch sau)
are pre-processed into digit form before extraction. This means "dedh sau ka
saman" is normalized to "150 ka saman" before pattern matching runs.

IMPORTANT: The extractor PROPOSES a transaction. The validator DISPOSES.
AI output is NEVER directly written to the ledger.
"""

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Tuple

from backend.config import Settings
from backend.schemas import (
    ExtractedCustomer,
    ExtractedFinancials,
    ExtractedItem,
    ExtractedTransaction,
    Intent,
    TransactionType,
)


# ── Hinglish Number Normalization ──────────────────────────────────────────────
#
# Two-pass system:
#   Pass 1: Replace multi-word compound patterns (longest match first)
#           "dedh sau" → "150", "dhai hazaar" → "2500"
#   Pass 2: Replace single-word Hindi numbers not adjacent to digits
#           "paanch" → "5", "sau" → "100"
#
# This ensures "dedh sau" is matched as a unit (→150) and NOT as
# "dedh" (→150) + "sau" (→100) separately.

HINDI_COMPOUND_NUMBERS: List[Tuple[str, int]] = [
    # ── 3-word compounds (checked first — longest match wins) ──

    # saadhe (साढ़े) = X.5 × 100 — formal form
    ("saadhe teen sau", 350),
    ("saadhe char sau", 450), ("saadhe chaar sau", 450),
    ("saadhe paanch sau", 550),
    ("saadhe chhe sau", 650),
    ("saadhe saat sau", 750),
    ("saadhe aath sau", 850),
    ("saadhe nau sau", 950),

    # sare / saare (सारे/साड़े) = colloquial form of saadhe — hundreds
    ("sare teen sau", 350), ("saare teen sau", 350),
    ("sare char sau", 450), ("saare char sau", 450),
    ("sare chaar sau", 450), ("saare chaar sau", 450),
    ("sare paanch sau", 550), ("saare paanch sau", 550),
    ("sare chhe sau", 650), ("saare chhe sau", 650),
    ("sare saat sau", 750), ("saare saat sau", 750),
    ("sare aath sau", 850), ("saare aath sau", 850),
    ("sare nau sau", 950), ("saare nau sau", 950),

    # saadhe / sare — thousands
    ("saadhe teen hazaar", 3500), ("sare teen hazaar", 3500), ("saare teen hazaar", 3500),
    ("saadhe char hazaar", 4500), ("sare char hazaar", 4500), ("saare char hazaar", 4500),
    ("saadhe chaar hazaar", 4500), ("sare chaar hazaar", 4500), ("saare chaar hazaar", 4500),
    ("saadhe paanch hazaar", 5500), ("sare paanch hazaar", 5500), ("saare paanch hazaar", 5500),

    # sawa (सवा) = 1.25× — "quarter more"
    ("sawa sau", 125), ("savaa sau", 125),
    ("sawa do sau", 225), ("savaa do sau", 225),
    ("sawa teen sau", 325), ("savaa teen sau", 325),
    ("sawa char sau", 425), ("savaa char sau", 425),
    ("sawa chaar sau", 425), ("savaa chaar sau", 425),
    ("sawa paanch sau", 525),
    ("sawa hazaar", 1250), ("savaa hazaar", 1250),
    ("sawa hazar", 1250), ("savaa hazar", 1250),
    ("sawa do hazaar", 2250), ("sawa teen hazaar", 3250),

    # paune / pone (पौने) = 0.75× — "quarter less"
    ("paune do sau", 175), ("pone do sau", 175), ("pauna do sau", 175),
    ("paune teen sau", 275), ("pone teen sau", 275),
    ("paune char sau", 375), ("pone char sau", 375),
    ("paune chaar sau", 375), ("pone chaar sau", 375),
    ("paune paanch sau", 475), ("pone paanch sau", 475),
    ("paune chhe sau", 575),
    ("paune saat sau", 675),
    ("paune aath sau", 775),
    ("paune nau sau", 875),
    ("paune do hazaar", 1750), ("pone do hazaar", 1750),
    ("paune teen hazaar", 2750),
    ("paune hazaar", 750), ("pone hazaar", 750),

    # ── 2-word compounds — thousands ──
    ("dedh hazaar", 1500), ("dedh hazar", 1500),
    ("dhai hazaar", 2500), ("dhai hazar", 2500), ("dhaai hazaar", 2500),
    ("do hazaar", 2000), ("do hazar", 2000),
    ("teen hazaar", 3000), ("char hazaar", 4000), ("chaar hazaar", 4000),
    ("paanch hazaar", 5000),
    ("chhe hazaar", 6000), ("saat hazaar", 7000), ("aath hazaar", 8000),
    ("nau hazaar", 9000), ("das hazaar", 10000),
    ("gyaarah hazaar", 11000), ("baarah hazaar", 12000),
    ("pandrah hazaar", 15000), ("bees hazaar", 20000),
    ("pacchees hazaar", 25000), ("tees hazaar", 30000),
    ("pachaas hazaar", 50000), ("ek laakh", 100000), ("ek lakh", 100000),

    # ── 2-word compounds — hundreds ──
    ("dedh sau", 150),
    ("dhai sau", 250), ("dhaai sau", 250),
    ("do sau", 200),
    ("teen sau", 300),
    ("char sau", 400), ("chaar sau", 400),
    ("paanch sau", 500),
    ("chhe sau", 600),
    ("saat sau", 700),
    ("aath sau", 800),
    ("nau sau", 900),
]

HINDI_SINGLE_NUMBERS = {
    # 1-9
    "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "paanch": "5", "panch": "5",
    "chhe": "6", "chhah": "6", "saat": "7", "aath": "8", "aatt": "8",
    "nau": "9",
    # 10-19
    "das": "10",
    "gyaarah": "11", "gyarah": "11",
    "baarah": "12", "barah": "12",
    "terah": "13",
    "chaudah": "14", "chaudaha": "14",
    "pandrah": "15", "pandhra": "15",
    "solah": "16", "sola": "16",
    "satrah": "17", "satara": "17",
    "athaarah": "18", "atharah": "18",
    "unees": "19", "unnees": "19",
    # 20-29
    "bees": "20", "bis": "20",
    "ikkees": "21", "ikkis": "21",
    "baees": "22", "bais": "22",
    "teyees": "23", "teis": "23",
    "chaubees": "24", "chaubis": "24",
    "pacchees": "25", "pachees": "25", "pachchis": "25",
    "chabbees": "26", "chhabbis": "26",
    "sattaees": "27", "sattais": "27",
    "atthaees": "28", "atthais": "28",
    "untees": "29", "untis": "29",
    # 30-90 (tens)
    "tees": "30", "tis": "30",
    "chaalees": "40", "chaalis": "40",
    "pachaas": "50", "pachas": "50",
    "saath": "60", "saatt": "60",
    "sattar": "70",
    "assi": "80", "assee": "80",
    "nabbe": "90", "nabbe": "90",
    # 100, 1000
    "sau": "100",
    "hazaar": "1000", "hazar": "1000",
    "laakh": "100000", "lakh": "100000",
    # Standalone fractional words (used when no compound matched)
    "dedh": "150", "dhai": "250", "dhaai": "250",
    "sawa": "125", "savaa": "125",
    "paune": "75", "pone": "75",
}


def normalize_hindi_numbers(text: str) -> str:
    """
    Pre-process transcript to convert Hindi word-form numbers to digits.

    Examples:
        "dedh sau ka saman" → "150 ka saman"
        "dhai hazaar ka bill" → "2500 ka bill"
        "paanch sau rupay" → "500 rupay"
        "teen sau ka tel aur do sau ka aata" → "300 ka tel aur 200 ka aata"
    """
    result = text.lower()

    # Pass 1: Replace multi-word compound patterns (longest match first)
    for phrase, value in HINDI_COMPOUND_NUMBERS:
        pattern = r'\b' + re.escape(phrase) + r'\b'
        result = re.sub(pattern, str(value), result, flags=re.IGNORECASE)

    # Pass 2: Replace remaining single-word Hindi numbers
    # Avoid double-converting: don't replace if already adjacent to a digit
    for word, digit in HINDI_SINGLE_NUMBERS.items():
        pattern = r'(?<!\d)\b' + re.escape(word) + r'\b(?!\s*\d)'
        result = re.sub(pattern, digit, result, flags=re.IGNORECASE)

    return result


# ── UPI / Digital Payment Detection ────────────────────────────────────────────

UPI_KEYWORDS = re.compile(
    r'\b(?:upi|phone\s*pe|phonepe|gpay|g\s*pay|google\s*pay|paytm|online|bhim)\b',
    re.IGNORECASE,
)


# ── Extraction System Prompt (for LLM providers) ─────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a financial transaction extractor for an Indian Kirana (grocery) store.

Your task is to extract structured financial data from Hinglish (Hindi + English) voice transcripts.

IMPORTANT RULES:
1. Extract EXACT amounts mentioned. Do NOT guess or approximate.
2. If amounts don't add up, report what was said - the validator will catch errors.
3. Distinguish between transaction types:
   - SALE: customer buys goods (total, with cash/UPI/credit split)
   - PAYMENT_RECEIVED: customer pays against existing debt/udhar
   - EXPENSE: merchant spends money
   - PURCHASE: merchant buys stock

HINGLISH FINANCIAL VOCABULARY:
- "udhar"/"udhaar" = credit (amount owed)
- "baaki" = remaining/outstanding amount
- "kal" = tomorrow (+1 day), "parso" = day after tomorrow (+2 days), "aaj" = today
- "cash"/"naqad" = cash payment
- "UPI"/"PhonePe"/"GPay"/"Paytm"/"online" = UPI payment
- "pura" = full/complete (all paid)
- "maal"/"saman"/"rashan"/"kirana" = goods/items
- "liya" = took/bought, "diya" = gave/paid
- "dega"/"denge" = will give/pay (future, implies credit)
- "purana" = old/previous

NUMBER PATTERNS:
- "dedh sau" = 150, "dhai sau" = 250, "saadhe teen sau" = 350
- "paanch sau" = 500, "dedh hazaar" = 1500, "dhai hazaar" = 2500

OUTPUT FORMAT (strict JSON):
{
  "intent": "sale"|"payment"|"expense"|"purchase",
  "transaction_type": "SALE"|"PAYMENT_RECEIVED"|"EXPENSE"|"PURCHASE",
  "customer": {"name": "<name>", "phone": null, "raw_mention": "<raw>"},
  "financials": {"total_amount": "<decimal>", "cash_paid": "<decimal>", "upi_paid": "<decimal>", "credit_amount": "<decimal>"},
  "items": [{"item_name": "<item>", "quantity": null, "price": "<decimal or null>"}],
  "due_date": "<YYYY-MM-DD or null>",
  "confidence_score": <0.0 to 1.0>,
  "flags": []
}
"""


# ── Provider Interface ─────────────────────────────────────────────────────────

class ExtractionProvider(ABC):
    """Abstract base class for structured extraction providers."""

    @abstractmethod
    def extract(self, transcript: str) -> ExtractedTransaction:
        """Extract structured transaction data from a transcript."""
        ...


class ExtractionError(Exception):
    """Raised when extraction fails."""
    def __init__(self, message: str, code: str = "ERR_EXTRACTION_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


# ── Mock Extraction Provider ───────────────────────────────────────────────────

class MockExtractionProvider(ExtractionProvider):
    """
    Deterministic regex-based extractor for common Hinglish financial sentences.

    Key capabilities:
    - Hindi word-form number conversion (dedh sau → 150, dhai hazaar → 2500)
    - Context-aware amount classification (which number is total/cash/UPI/credit)
    - Intent detection (sale vs payment_received vs expense)
    - Customer name extraction with honorific preservation
    - Hinglish temporal expression parsing (kal, parso, hafta)
    """

    def extract(self, transcript: str) -> ExtractedTransaction:
        """Parse Hinglish transcript using pattern matching."""
        original = transcript.strip()

        # CRITICAL STEP: normalize Hindi word-form numbers to digits
        normalized = normalize_hindi_numbers(original)
        text = normalized.lower()

        customer_name = self._extract_customer(text, original)
        intent, txn_type = self._detect_intent(text)
        numbers_ctx = self._extract_numbers_with_context(text)
        financials, extraction_flags = self._calculate_financials(text, numbers_ctx, intent)
        items = self._extract_items(text, financials.total_amount)
        due_date = self._extract_due_date(text)

        return ExtractedTransaction(
            intent=intent,
            transaction_type=txn_type,
            customer=ExtractedCustomer(
                name=customer_name, phone=None, raw_mention=customer_name,
            ),
            financials=financials,
            items=items,
            due_date=due_date,
            confidence_score=0.90,
            flags=extraction_flags,
        )

    # ── Customer Name ──────────────────────────────────────────────────────────

    def _extract_customer(self, text: str, original: str) -> str:
        """Extract customer name from transcript with proper casing."""
        patterns = [
            r"^(.+?)\s+ne\s+",
            r"^(.+?)\s+ka\s+(?:purana|pichla|bill|udh?aar|baaki)",
            r"^(.+?)\s+ka\s+\d+",
            r"^(.+?)\s+ko\s+",
            r"^(.+?)\s+ka\s+",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name_lower = match.group(1).strip()
                # Map back to original casing
                orig_words = original.split()
                n_words = len(name_lower.split())
                if n_words <= len(orig_words):
                    return " ".join(orig_words[:n_words])
                return name_lower.title()
        return "Unknown Customer"

    # ── Intent Detection ───────────────────────────────────────────────────────

    def _detect_intent(self, text: str) -> tuple:
        """Detect transaction intent from text patterns."""
        payment_patterns = [
            r"purana\s+udh?aar", r"pichla\s+baaki",
            r"udh?aar\s+tha", r"baaki\s+tha",
            r"chuka\s+diya", r"wapas\s+diya",
            r"jama\s+kar", r"payment\s+diya",
        ]
        for p in payment_patterns:
            if re.search(p, text):
                return Intent.PAYMENT, TransactionType.PAYMENT_RECEIVED

        expense_words = ["kharcha", "expense", "bill bhara", "bijli", "rent", "kiraya"]
        if any(w in text for w in expense_words):
            return Intent.EXPENSE, TransactionType.EXPENSE

        return Intent.SALE, TransactionType.SALE

    # ── Number Extraction with Context ─────────────────────────────────────────

    def _extract_numbers_with_context(self, text: str) -> List[Tuple[Decimal, str, int]]:
        """
        Extract all numbers from text with surrounding context.
        Returns [(value, context_string, position), ...]
        """
        results = []
        for match in re.finditer(r'(\d+)', text):
            value = Decimal(match.group(1))
            pos = match.start()
            ctx_start = max(0, pos - 30)
            ctx_end = min(len(text), match.end() + 30)
            context = text[ctx_start:ctx_end]
            results.append((value, context, pos))
        return results

    # ── Financial Calculation ──────────────────────────────────────────────────

    def _calculate_financials(
        self, text: str, numbers_ctx: List[Tuple[Decimal, str, int]], intent: Intent
    ) -> Tuple[ExtractedFinancials, List[str]]:
        """
        Context-aware financial calculation.

        Strategy:
        1. Check for "pura cash/UPI/udhar" shortcuts
        2. For PAYMENT_RECEIVED: second number is the actual payment
        3. For SALE: first number = total, classify rest by context words
        4. Infer credit from baaki/udhar indicators
        """
        flags: List[str] = []

        if not numbers_ctx:
            return ExtractedFinancials(
                total_amount=Decimal("0"), cash_paid=Decimal("0"),
                upi_paid=Decimal("0"), credit_amount=Decimal("0"),
            ), flags

        all_values = [n[0] for n in numbers_ctx]
        total = all_values[0]

        # ── "pura X" shortcuts ──
        if re.search(r'pura\s+cash|sab\s+cash|poora\s+cash', text):
            return ExtractedFinancials(total_amount=total, cash_paid=total, upi_paid=Decimal("0"), credit_amount=Decimal("0")), flags
        if re.search(r'pura\s+upi|pura\s+online|sab\s+upi', text):
            return ExtractedFinancials(total_amount=total, cash_paid=Decimal("0"), upi_paid=total, credit_amount=Decimal("0")), flags
        if re.search(r'pura\s+udh?aar|sab\s+udh?aar|poora\s+udh?aar', text):
            return ExtractedFinancials(total_amount=total, cash_paid=Decimal("0"), upi_paid=Decimal("0"), credit_amount=total), flags

        # ── Payment received ──
        if intent == Intent.PAYMENT:
            if len(all_values) >= 2:
                payment = all_values[1]
            else:
                payment = all_values[0]
            cash = Decimal("0")
            upi = Decimal("0")
            if UPI_KEYWORDS.search(text):
                upi = payment
            else:
                cash = payment
            return ExtractedFinancials(total_amount=payment, cash_paid=cash, upi_paid=upi, credit_amount=Decimal("0")), flags

        # ── Sale: classify amounts by context ──
        cash = Decimal("0")
        upi = Decimal("0")
        credit = Decimal("0")

        # Explicit "X cash aur Y UPI" compound
        cash_upi = re.search(
            r'(\d+)\s*cash\s*(?:aur|and|,|or)\s*(\d+)\s*(?:upi|online|phone\s*pe|gpay|paytm)',
            text, re.IGNORECASE,
        )
        if cash_upi:
            cash = Decimal(cash_upi.group(1))
            upi = Decimal(cash_upi.group(2))
        else:
            # Classify each subsequent number by surrounding words
            for value, context, pos in numbers_ctx[1:]:
                ctx = context.lower()
                if re.search(r'cash|naqad|naqd', ctx):
                    cash = value
                elif UPI_KEYWORDS.search(ctx):
                    upi = value
                elif re.search(r'udh?aar|credit|baaki', ctx):
                    credit = value
                else:
                    # Unlabeled: check broader text for "diya" (gave = cash) vs "kiya" (did = UPI)
                    num_str = str(int(value))
                    if re.search(num_str + r'\s+(?:diya|de\s+diya|rupay?\s+diya)', text):
                        cash = value
                    elif re.search(num_str + r'\s+(?:kiya|kar\s+diya)', text):
                        upi = value
                    elif cash == Decimal("0"):
                        cash = value
                    elif upi == Decimal("0"):
                        upi = value

        # ── Infer credit from baaki/udhar indicators ──
        has_credit_indicator = bool(re.search(
            r'baaki|udh?aar|kal\s+de|dega|denge|degi|baad\s+mein|likh\s+do|likh\s+le',
            text,
        ))

        if has_credit_indicator and credit == Decimal("0"):
            inferred = total - cash - upi
            if inferred > Decimal("0"):
                credit = inferred
            elif inferred < Decimal("0"):
                # cash + upi > total with credit indicator — flag the inconsistency
                flags.append("ERR_INFERRED_NEGATIVE_CREDIT")

        # If no credit indicator and no split info, assume full cash
        if not has_credit_indicator and cash + upi == Decimal("0") and total > Decimal("0"):
            if len(all_values) == 1:
                cash = total

        return ExtractedFinancials(
            total_amount=total,
            cash_paid=cash,
            upi_paid=upi,
            credit_amount=credit,
        ), flags

    # ── Item Extraction ────────────────────────────────────────────────────────

    def _extract_items(self, text: str, total: Decimal) -> List[ExtractedItem]:
        """Extract item descriptions from text."""
        items = []
        ITEM_WORDS = r'rashan|saman|maal|kirana|tel|aata|cheeni|daal|chaawal|sabzi|doodh|sugar'

        # "X ka item" pattern
        for m in re.finditer(r'(\d+)\s+ka\s+(' + ITEM_WORDS + r')', text, re.IGNORECASE):
            items.append(ExtractedItem(item_name=m.group(2), quantity=None, price=Decimal(m.group(1))))

        # "ka item" without explicit price
        if not items:
            for m in re.finditer(r'ka\s+(' + ITEM_WORDS + r')', text, re.IGNORECASE):
                items.append(ExtractedItem(item_name=m.group(1), quantity=None, price=total if total > 0 else None))

        # Compound: "X ka tel aur Y ka aata"
        if not items:
            compounds = re.findall(r'(\d+)\s+ka\s+(\w+)', text)
            for amount, item in compounds:
                if item not in ('purana', 'pichla', 'bill'):
                    items.append(ExtractedItem(item_name=item, quantity=None, price=Decimal(amount)))

        # Fallback
        if not items and total > Decimal("0"):
            name = self._detect_item_name(text)
            items.append(ExtractedItem(item_name=name, quantity=None, price=total))

        return items

    def _detect_item_name(self, text: str) -> str:
        """Detect the most likely item category from text."""
        for pattern, name in [
            (r'\brashan\b', 'rashan'), (r'\bsaman\b', 'saman'),
            (r'\bmaal\b', 'maal'), (r'\bkirana\b', 'kirana'),
            (r'\btel\b', 'tel'), (r'\baata\b', 'aata'),
            (r'\bcheeni\b', 'cheeni'), (r'\bdaal\b', 'daal'),
        ]:
            if re.search(pattern, text):
                return name
        return "general goods"

    # ── Due Date ───────────────────────────────────────────────────────────────

    def _extract_due_date(self, text: str) -> Optional[str]:
        """Extract due date from Hinglish temporal expressions."""
        today = datetime.now(timezone.utc).date()

        if re.search(r'\bkal\b', text):
            return (today + timedelta(days=1)).isoformat()
        if re.search(r'\bparso\b|\bparsoo\b', text):
            return (today + timedelta(days=2)).isoformat()
        if re.search(r'\baaj\b', text):
            return today.isoformat()
        if re.search(r'\bhafta\b|\bhafte\b', text):
            return (today + timedelta(days=7)).isoformat()
        if re.search(r'\bmahina\b|\bmahine\b', text):
            return (today + timedelta(days=30)).isoformat()

        din_match = re.search(r'(\d+)\s*din', text)
        if din_match:
            return (today + timedelta(days=int(din_match.group(1)))).isoformat()

        return None


# ── OpenAI Extraction Provider ─────────────────────────────────────────────────

class OpenAIExtractionProvider(ExtractionProvider):
    """Extract structured data using OpenAI's structured JSON output."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def extract(self, transcript: str) -> ExtractedTransaction:
        try:
            import httpx

            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Extract transaction from: \"{transcript}\""},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return ExtractedTransaction(**parsed)

        except ImportError:
            raise ExtractionError("httpx package required for OpenAI provider")
        except Exception as e:
            raise ExtractionError(f"OpenAI extraction failed: {str(e)}")


# ── Groq Extraction Provider ──────────────────────────────────────────────────

class GroqExtractionProvider(ExtractionProvider):
    """Extract structured data using Groq's API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def extract(self, transcript: str) -> ExtractedTransaction:
        try:
            import httpx

            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-70b-versatile",
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Extract transaction from: \"{transcript}\""},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return ExtractedTransaction(**parsed)

        except ImportError:
            raise ExtractionError("httpx package required for Groq provider")
        except Exception as e:
            raise ExtractionError(f"Groq extraction failed: {str(e)}")


# ── Provider Factory ──────────────────────────────────────────────────────────

def get_extraction_provider(settings: Settings) -> ExtractionProvider:
    """Factory: create the appropriate extraction provider based on configuration."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "mock":
        return MockExtractionProvider()
    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ExtractionError("OPENAI_API_KEY is required for OpenAI extraction provider")
        return OpenAIExtractionProvider(settings.OPENAI_API_KEY)
    elif provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ExtractionError("GROQ_API_KEY is required for Groq extraction provider")
        return GroqExtractionProvider(settings.GROQ_API_KEY)
    else:
        raise ExtractionError(f"Unknown LLM provider: {provider}")
