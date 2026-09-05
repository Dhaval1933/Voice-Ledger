"""
Pydantic v2 request/response models for all API contracts.

These schemas define the strict contracts between:
- Frontend ↔ Backend API
- AI extraction layer → Validation layer
- Validation layer → Commit layer

All monetary fields use Decimal with explicit serialization.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────────

class TransactionType(str, Enum):
    SALE = "SALE"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    EXPENSE = "EXPENSE"
    PURCHASE = "PURCHASE"


class LedgerStatus(str, Enum):
    COMMITTED = "COMMITTED"
    FLAGGED = "FLAGGED"
    VOID = "VOID"


class RecoveryStatus(str, Enum):
    PENDING = "PENDING"
    LINK_SENT = "LINK_SENT"
    COLLECTED = "COLLECTED"


class Intent(str, Enum):
    SALE = "sale"
    PAYMENT = "payment"
    EXPENSE = "expense"
    PURCHASE = "purchase"


# ── Extraction Models (AI output contract) ─────────────────────────────────────

class ExtractedCustomer(BaseModel):
    """Customer info extracted from voice transcript."""
    name: str
    phone: Optional[str] = None
    raw_mention: str


class ExtractedFinancials(BaseModel):
    """Financial breakdown extracted from voice transcript."""
    total_amount: Decimal = Field(ge=0)
    cash_paid: Decimal = Field(ge=0, default=Decimal("0.00"))
    upi_paid: Decimal = Field(ge=0, default=Decimal("0.00"))
    credit_amount: Decimal = Field(ge=0, default=Decimal("0.00"))


class ExtractedItem(BaseModel):
    """Line item extracted from voice transcript."""
    item_name: str
    quantity: Optional[str] = None
    price: Optional[Decimal] = None


class ExtractedTransaction(BaseModel):
    """Complete structured extraction from a voice transcript.
    This is what the AI/mock extractor produces."""
    intent: Intent
    transaction_type: TransactionType
    customer: ExtractedCustomer
    financials: ExtractedFinancials
    items: List[ExtractedItem] = Field(default_factory=list)
    due_date: Optional[str] = None  # ISO date string YYYY-MM-DD
    confidence_score: float = Field(ge=0, le=1, default=0.85)
    flags: List[str] = Field(default_factory=list)


# ── Validation Models ──────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    """Result of financial invariant validation."""
    valid: bool
    flag_code: Optional[str] = None
    delta: Decimal = Decimal("0.00")
    flags: List[str] = Field(default_factory=list)
    message: Optional[str] = None


# ── Customer Matching Models ───────────────────────────────────────────────────

class CustomerMatchCandidate(BaseModel):
    """A potential customer match."""
    id: str
    name: str
    phone: Optional[str] = None
    score: float
    method: str  # "exact_phone", "fuzzy_name", "exact_name"


class CustomerMatchResult(BaseModel):
    """Result of customer matching against merchant's customer base."""
    matched_customer: Optional[CustomerMatchCandidate] = None
    match_score: float = 0.0
    match_method: str = "none"
    is_ambiguous: bool = False
    is_new_customer: bool = False
    candidates: List[CustomerMatchCandidate] = Field(default_factory=list)


# ── Voice Process Response ─────────────────────────────────────────────────────

class VoiceProcessResponse(BaseModel):
    """Response from POST /api/voice/process — the verified draft."""
    transcript: str
    draft: ExtractedTransaction
    customer_match: CustomerMatchResult
    validation: ValidationResult
    can_commit: bool
    idempotency_hash: str
    flags: List[str] = Field(default_factory=list)


# ── Commit Models ──────────────────────────────────────────────────────────────

class CommitItemRequest(BaseModel):
    """Item to commit with the ledger entry."""
    item_name: str
    quantity: Optional[str] = None
    unit_price: Optional[Decimal] = None


class CommitRequest(BaseModel):
    """Request body for POST /api/ledger/commit.
    The merchant confirms the draft and sends this for atomic recording."""
    merchant_id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None  # For new customer creation
    customer_phone: Optional[str] = None
    transaction_type: TransactionType
    total_amount: Decimal = Field(ge=0)
    cash_paid: Decimal = Field(ge=0, default=Decimal("0.00"))
    upi_paid: Decimal = Field(ge=0, default=Decimal("0.00"))
    credit_amount: Decimal = Field(ge=0, default=Decimal("0.00"))
    due_date: Optional[str] = None
    items: List[CommitItemRequest] = Field(default_factory=list)
    raw_transcript: str = ""
    confidence_score: float = 0.85
    idempotency_hash: str


class CommitResponse(BaseModel):
    """Response from POST /api/ledger/commit."""
    success: bool
    ledger_entry_id: str
    customer_id: str
    customer_outstanding: Decimal
    recovery_id: Optional[str] = None
    upi_deep_link: Optional[str] = None
    message: str


# ── Ledger Summary ─────────────────────────────────────────────────────────────

class LedgerSummary(BaseModel):
    """Daily financial summary for the KPI dashboard."""
    total_sales: Decimal = Decimal("0.00")
    cash_in_hand: Decimal = Decimal("0.00")
    upi_collected: Decimal = Decimal("0.00")
    total_credit_given: Decimal = Decimal("0.00")
    outstanding_udhaar: Decimal = Decimal("0.00")
    overdue_recoveries: int = 0


# ── Ledger Entry Response ─────────────────────────────────────────────────────

class TransactionItemResponse(BaseModel):
    """Transaction item in ledger entry response."""
    id: str
    item_name: str
    quantity: Optional[str] = None
    unit_price: Optional[Decimal] = None


class PaymentRecoveryResponse(BaseModel):
    """Payment recovery info in ledger entry response."""
    id: str
    amount: Decimal
    upi_deep_link: Optional[str] = None
    razorpay_link_id: Optional[str] = None
    razorpay_short_url: Optional[str] = None
    scheduled_reminder_date: Optional[str] = None
    status: str


class LedgerEntryResponse(BaseModel):
    """Single ledger entry for the history feed."""
    id: str
    merchant_id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    transaction_type: str
    total_amount: Decimal
    cash_paid: Decimal
    upi_paid: Decimal
    credit_amount: Decimal
    due_date: Optional[str] = None
    raw_transcript: Optional[str] = None
    confidence_score: Optional[float] = None
    status: str
    created_at: str
    items: List[TransactionItemResponse] = Field(default_factory=list)
    recovery: Optional[PaymentRecoveryResponse] = None


class PaginatedLedgerResponse(BaseModel):
    """Paginated ledger entries response."""
    entries: List[LedgerEntryResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


# ── Recovery Models ────────────────────────────────────────────────────────────

class RecoveryReminderRequest(BaseModel):
    """Request to send a WhatsApp recovery reminder."""
    recovery_id: str
    merchant_id: str


class RecoveryReminderResponse(BaseModel):
    """Response from the WhatsApp reminder mock."""
    success: bool
    whatsapp_url: str
    message: str
    recovery_status: str = "LINK_SENT"


class CustomerWithDues(BaseModel):
    """Customer with pending Udhar for the recovery feed."""
    id: str
    name: str
    phone: Optional[str] = None
    total_outstanding: Decimal
    latest_due_date: Optional[str] = None
    is_overdue: bool = False
    recovery_id: Optional[str] = None
    recovery_status: Optional[str] = None
    upi_deep_link: Optional[str] = None
    razorpay_link_id: Optional[str] = None
    razorpay_short_url: Optional[str] = None


# ── Error Models ───────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Structured error detail."""
    code: str
    message: str
    details: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Structured error response wrapper."""
    error: ErrorDetail


# ── Auth Models ────────────────────────────────────────────────────────────────

class UserSignUpRequest(BaseModel):
    """User registration request."""
    email: str = Field(..., description="Unique email address")
    name: str = Field(..., description="First name")
    surname: str = Field(..., description="Surname / Last name")
    shop_name: str = Field(..., description="Name of the shop")
    phone: str = Field(..., description="Phone number")
    password: str = Field(..., min_length=6, description="Password (at least 6 characters)")


class UserLoginRequest(BaseModel):
    """User login request."""
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    """Password change request for authenticated user."""
    current_password: str
    new_password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    """Public user profile response."""
    id: str
    email: str
    name: str
    surname: str
    shop_name: str
    phone: str
    merchant_id: Optional[str] = None
    created_at: Optional[str] = None


class AuthTokenResponse(BaseModel):
    """JWT authorization token and user profile."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ForgotPasswordRequest(BaseModel):
    """Request to initiate password reset via email."""
    email: str = Field(..., description="Registered email address")


class ForgotPasswordResponse(BaseModel):
    """Response after initiating password reset."""
    success: bool
    message: str
    simulated_email: Optional[dict] = None


class VerifyResetTokenRequest(BaseModel):
    """Request to verify a reset token or OTP code."""
    token: Optional[str] = None
    code: Optional[str] = None
    email: Optional[str] = None


class VerifyResetTokenResponse(BaseModel):
    """Response verifying validity of a reset token or code."""
    valid: bool
    email: Optional[str] = None
    token: Optional[str] = None
    message: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    """Request to set a new password."""
    token: Optional[str] = None
    code: Optional[str] = None
    email: Optional[str] = None
    new_password: str = Field(..., min_length=6, description="New password (min 6 characters)")


class ResetPasswordResponse(BaseModel):
    """Response after setting a new password."""
    success: bool
    message: str


# ── Razorpay Payment Rails Models ──────────────────────────────────────────────

class RazorpayLinkCreateRequest(BaseModel):
    """Request to generate a Razorpay Payment Link for customer recovery."""
    recovery_id: str
    customer_id: Optional[str] = None
    amount: Optional[Decimal] = None


class RazorpayLinkResponse(BaseModel):
    """Generated Razorpay Payment Link details."""
    recovery_id: str
    razorpay_link_id: str
    short_url: str
    qr_code_url: Optional[str] = None
    upi_intent_url: Optional[str] = None
    amount: Decimal
    customer_name: str
    status: str


class SimulatePaymentRequest(BaseModel):
    """Request to simulate customer completing payment via Razorpay."""
    recovery_id: str
    amount: Optional[Decimal] = None


class SimulatePaymentResponse(BaseModel):
    """Response from simulated Razorpay payment collection."""
    success: bool
    message: str
    razorpay_payment_id: str
    recovery_id: str
    customer_name: str
    amount_paid: Decimal
    new_outstanding: Decimal
    recovery_status: str


class SettlePaymentRequest(BaseModel):
    """Request to directly settle a customer due via Cash or UPI."""
    customer_id: str
    recovery_id: Optional[str] = None
    amount: Decimal = Field(..., gt=0)
    payment_mode: str = Field(default="CASH")  # "CASH", "UPI", "RAZORPAY"
    notes: Optional[str] = None


class SettlePaymentResponse(BaseModel):
    """Response when a customer due is settled."""
    success: bool = True
    message: str
    entry_id: str
    amount_paid: Decimal
    payment_mode: str
    remaining_balance: Decimal
    customer_name: str

