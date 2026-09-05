"""
FastAPI application -- Voice Ledger & AI Finance Controller.

API Endpoints:
    POST /api/voice/process      — Voice → transcript → extraction → validation → draft
    POST /api/ledger/commit      — Atomic ledger commit with server-side revalidation
    GET  /api/ledger/summary     — Daily financial KPI summary
    GET  /api/ledger/entries     — Paginated ledger history
    POST /api/recovery/send-reminder — Mock WhatsApp recovery reminder
    POST /api/demo/seed          — Load demo data
    GET  /api/health             — Health check
    GET  /api/customers/dues     — Customers with outstanding balances

Architecture:
    Audio → ASR → Extraction → Sanitization → Validation → Customer Matching → Draft
    Draft → Merchant Confirmation → Server Revalidation → Atomic Commit → Balance Update → Recovery
"""

import math
import re
import secrets
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Query, Form, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload

from backend.config import get_settings, Settings
from backend.database import init_db, get_db
from backend.extractor import get_extraction_provider, ExtractionError
from backend.models import (
    Merchant, Customer, LedgerEntry, TransactionItem, PaymentRecovery, User,
    PasswordResetToken, gen_uuid, utcnow,
)
from backend.schemas import (
    CommitRequest, CommitResponse, ErrorDetail, ErrorResponse,
    LedgerEntryResponse, LedgerSummary, PaginatedLedgerResponse,
    PaymentRecoveryResponse, RecoveryReminderRequest, RecoveryReminderResponse,
    TransactionItemResponse, ValidationResult, VoiceProcessResponse,
    CustomerWithDues,
    UserSignUpRequest, UserLoginRequest, ChangePasswordRequest,
    UserResponse, AuthTokenResponse,
    ForgotPasswordRequest, ForgotPasswordResponse,
    VerifyResetTokenRequest, VerifyResetTokenResponse,
    ResetPasswordRequest, ResetPasswordResponse,
    RazorpayLinkCreateRequest, RazorpayLinkResponse,
    SimulatePaymentRequest, SimulatePaymentResponse,
    SettlePaymentRequest, SettlePaymentResponse,
)
from backend.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_current_merchant,
)

from backend.services.customer_matching import match_customer
from backend.services.recovery import (
    generate_upi_deep_link, generate_whatsapp_reminder, format_indian_currency,
)
from backend.services.email_service import (
    send_password_reset_email, get_latest_simulated_email,
)
from backend.services.razorpay_service import (
    create_razorpay_payment_link, verify_razorpay_webhook_signature,
    reconcile_recovery_payment,
)
from backend.services.transcription import (
    ASRError, get_asr_provider, validate_audio, MockASRProvider,
)
from backend.validator import (
    generate_idempotency_hash, sanitize_transcript, validate_financial_invariant,
    safe_decimal,
)


# ── App Setup ──────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database on startup."""
    init_db()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Voice Ledger",
        description="AI Finance Controller for Indian Kirana Merchants",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()


# ── Error Handlers ─────────────────────────────────────────────────────────────

def error_response(code: str, message: str, details: dict = None, status: int = 400):
    """Create a structured error response. Never expose stack traces."""
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, details=details)
        ).model_dump(),
    )


# ── Health Check ───────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    """Basic health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "asr_provider": settings.ASR_PROVIDER,
        "llm_provider": settings.LLM_PROVIDER,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Authentication Endpoints ───────────────────────────────────────────────────

@app.post("/api/auth/signup", response_model=AuthTokenResponse)
def signup(request: UserSignUpRequest, db: Session = Depends(get_db)):
    """
    Sign up a new merchant/shopkeeper.
    Takes email (unique), name, surname, shop_name, phone, password.
    Encrypts password with bcrypt hash.
    Creates User and Merchant records.
    Returns JWT access token and user profile.
    """
    email_clean = request.email.strip().lower()
    name_clean = request.name.strip()
    surname_clean = request.surname.strip()
    shop_name_clean = request.shop_name.strip()
    phone_clean = request.phone.strip()

    # Validate required text fields
    if not name_clean or not surname_clean or not shop_name_clean or not phone_clean:
        return error_response(
            "ERR_INVALID_INPUT",
            "Name, surname, shop name, and phone number cannot be empty.",
            status=400,
        )

    # Validate email format
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email_clean):
        return error_response(
            "ERR_INVALID_EMAIL",
            "Please provide a valid email address.",
            status=400,
        )

    # Validate phone digits
    phone_digits = re.sub(r"\D", "", phone_clean)
    if len(phone_digits) < 7:
        return error_response(
            "ERR_INVALID_PHONE",
            "Please provide a valid phone number (at least 7 digits).",
            status=400,
        )

    # Check if email is already taken
    existing_user = db.query(User).filter(func.lower(User.email) == email_clean).first()
    if existing_user:
        return error_response(
            "ERR_EMAIL_EXISTS",
            "An account with this email address already exists.",
            status=400,
        )

    # Validate password length
    if len(request.password) < 6:
        return error_response(
            "ERR_WEAK_PASSWORD",
            "Password must be at least 6 characters long.",
            status=400,
        )

    # Encrypt password using bcrypt hash
    hashed = hash_password(request.password)

    # Create User record
    user_id = gen_uuid()
    user = User(
        id=user_id,
        email=email_clean,
        name=name_clean,
        surname=surname_clean,
        shop_name=shop_name_clean,
        phone=phone_clean,
        password_hash=hashed,
    )
    db.add(user)
    db.flush()

    # Create Merchant record for this user
    merchant_id = gen_uuid()
    merchant = Merchant(
        id=merchant_id,
        user_id=user.id,
        business_name=user.shop_name,
        phone=user.phone,
        vpa_upi_id=f"{user.phone}@upi",
    )

    db.add(merchant)
    db.commit()
    db.refresh(user)
    db.refresh(merchant)

    # Generate JWT token
    token = create_access_token({"sub": user.id, "email": user.email})

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            surname=user.surname,
            shop_name=user.shop_name,
            phone=user.phone,
            merchant_id=merchant.id,
            created_at=user.created_at.isoformat() if user.created_at else None,
        ),
    )


@app.post("/api/auth/login", response_model=AuthTokenResponse)
def login(request: UserLoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate a user with email and password.
    Verifies bcrypt password hash.
    Returns JWT access token and user profile.
    """
    email_clean = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email_clean).first()
    if not user or not verify_password(request.password, user.password_hash):
        return error_response(
            "ERR_INVALID_CREDENTIALS",
            "Invalid email or password.",
            status=401,
        )

    merchant = db.query(Merchant).filter(Merchant.user_id == user.id).first()
    if not merchant:
        merchant = Merchant(
            id=gen_uuid(),
            user_id=user.id,
            business_name=user.shop_name,
            phone=user.phone,
            vpa_upi_id=f"{user.phone}@upi",
        )
        db.add(merchant)
        db.commit()
        db.refresh(merchant)

    token = create_access_token({"sub": user.id, "email": user.email})

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            surname=user.surname,
            shop_name=user.shop_name,
            phone=user.phone,
            merchant_id=merchant.id,
            created_at=user.created_at.isoformat() if user.created_at else None,
        ),
    )


@app.get("/api/auth/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    current_merchant: Merchant = Depends(get_current_merchant),
):
    """Return the profile of the currently logged in user."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        surname=current_user.surname,
        shop_name=current_user.shop_name,
        phone=current_user.phone,
        merchant_id=current_merchant.id,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
    )


@app.post("/api/auth/change-password")
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change password for the currently logged-in user.
    Verifies current password with bcrypt, then updates with new bcrypt hash.
    """
    if not verify_password(request.current_password, current_user.password_hash):
        return error_response(
            "ERR_INCORRECT_PASSWORD",
            "Current password does not match.",
            status=400,
        )

    if len(request.new_password) < 6:
        return error_response(
            "ERR_WEAK_PASSWORD",
            "New password must be at least 6 characters long.",
            status=400,
        )

    if request.current_password == request.new_password:
        return error_response(
            "ERR_SAME_PASSWORD",
            "New password cannot be the same as the current password.",
            status=400,
        )

    current_user.password_hash = hash_password(request.new_password)
    db.commit()

    return {"success": True, "message": "Password changed successfully."}


@app.post("/api/auth/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Request a password reset email.
    Generates a secure 64-character token and 6-digit OTP code with 15-minute expiry.
    Sends branded HTML email (or captures in simulated mailbox for zero-config hackathon demoing).
    """
    settings = get_settings()
    email_clean = request.email.strip().lower()

    user = db.query(User).filter(func.lower(User.email) == email_clean).first()
    if not user:
        return ForgotPasswordResponse(
            success=False,
            message="No account found with this email address. Please check your email or register your shop.",
        )

    # Invalidate any existing unused reset tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,
    ).update({"used": True})

    # Generate secure 64-character token and random 6-digit OTP code
    token_str = secrets.token_urlsafe(32)
    code_str = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)

    reset_record = PasswordResetToken(
        id=gen_uuid(),
        user_id=user.id,
        token=token_str,
        code=code_str,
        expires_at=expires_at,
        used=False,
    )
    db.add(reset_record)
    db.commit()

    # Dispatch email (live SMTP or simulated mailbox)
    email_payload = send_password_reset_email(
        user_email=user.email,
        user_name=user.name,
        reset_token=token_str,
        reset_code=code_str,
        expires_in_minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES,
    )

    return ForgotPasswordResponse(
        success=True,
        message=f"Password reset instructions sent to {user.email}.",
        simulated_email=email_payload,
    )


@app.get("/api/auth/verify-reset-token", response_model=VerifyResetTokenResponse)
def verify_reset_token(
    token: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Verify if a reset token or OTP code is valid and unexpired."""
    now = datetime.now(timezone.utc)
    query = db.query(PasswordResetToken).filter(PasswordResetToken.used == False)

    if token:
        reset_token = query.filter(PasswordResetToken.token == token.strip()).first()
    elif code and email:
        email_clean = email.strip().lower()
        user = db.query(User).filter(func.lower(User.email) == email_clean).first()
        if not user:
            return VerifyResetTokenResponse(valid=False, message="User not found.")
        reset_token = query.filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.code == code.strip(),
        ).first()
    else:
        return VerifyResetTokenResponse(valid=False, message="Token or Code with Email required.")

    if not reset_token:
        return VerifyResetTokenResponse(valid=False, message="Invalid or already used reset code.")

    expires_at = reset_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        return VerifyResetTokenResponse(valid=False, message="Reset code has expired. Please request a new one.")

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    return VerifyResetTokenResponse(
        valid=True,
        email=user.email if user else None,
        token=reset_token.token,
        message="Valid reset token.",
    )


@app.post("/api/auth/reset-password", response_model=ResetPasswordResponse)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset user password using token or OTP code."""
    if len(request.new_password) < 6:
        return error_response("ERR_WEAK_PASSWORD", "New password must be at least 6 characters.", status=400)

    now = datetime.now(timezone.utc)
    query = db.query(PasswordResetToken).filter(PasswordResetToken.used == False)

    if request.token:
        reset_token = query.filter(PasswordResetToken.token == request.token.strip()).first()
    elif request.code and request.email:
        email_clean = request.email.strip().lower()
        user = db.query(User).filter(func.lower(User.email) == email_clean).first()
        if not user:
            return error_response("ERR_USER_NOT_FOUND", "User account not found.", status=404)
        reset_token = query.filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.code == request.code.strip(),
        ).first()
    else:
        return error_response("ERR_INVALID_REQUEST", "Either valid reset token or code + email is required.", status=400)

    if not reset_token:
        return error_response("ERR_INVALID_TOKEN", "Reset token is invalid or has already been used.", status=400)

    expires_at = reset_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        return error_response("ERR_EXPIRED_TOKEN", "Reset code has expired. Please request a new one.", status=400)

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        return error_response("ERR_USER_NOT_FOUND", "User not found.", status=404)

    # Update password and mark token as used
    user.password_hash = hash_password(request.new_password)
    reset_token.used = True
    db.commit()

    return ResetPasswordResponse(
        success=True,
        message="Password has been reset successfully. You can now log in with your new password.",
    )


@app.get("/api/auth/latest-simulated-email")
def get_latest_email(email: Optional[str] = Query(None)):
    """Fetch the latest simulated email for demo inspection & in-app testing."""
    item = get_latest_simulated_email(email)
    if not item:
        return JSONResponse(status_code=404, content={"message": "No simulated email found."})
    return item



# ── Voice Process ──────────────────────────────────────────────────────────────

@app.post("/api/voice/process")
async def voice_process(
    audio: Optional[UploadFile] = File(None),
    transcript_text: Optional[str] = Form(None),
    demo_index: Optional[int] = Form(None),
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Process a voice note into a verified transaction draft.

    Pipeline: audio → ASR → extraction → sanitization → validation → customer matching → draft

    Accepts either:
    - audio file (multipart upload)
    - transcript_text (direct text input for fallback/testing)
    - demo_index (select a specific demo transcript, 0-4)
    """
    settings = get_settings()
    merchant_id = current_merchant.id
    merchant = current_merchant


    # ── Step 1: Get transcript ──
    transcript = None

    if transcript_text:
        # Direct text input (fallback mode)
        transcript = transcript_text
    elif demo_index is not None:
        # Demo mode — pick a specific demo transcript
        asr = get_asr_provider(settings)
        if isinstance(asr, MockASRProvider):
            transcript = asr.get_demo_transcript(demo_index)
        else:
            transcript = asr.get_demo_transcript(demo_index) if hasattr(asr, 'get_demo_transcript') else None
            if not transcript:
                from backend.services.transcription import DEMO_TRANSCRIPT_MAP
                transcript = DEMO_TRANSCRIPT_MAP.get(demo_index, DEMO_TRANSCRIPT_MAP[0])
    elif audio:
        # Audio file upload
        try:
            audio_bytes = await audio.read()
            content_type = audio.content_type or "audio/webm"

            # Validate audio
            validate_audio(audio_bytes, content_type, settings.MAX_AUDIO_SIZE_MB)

            # Transcribe
            asr = get_asr_provider(settings)
            transcript = asr.transcribe(audio_bytes, content_type)

        except ASRError as e:
            return error_response(e.code, e.message)
        except Exception as e:
            return error_response("ERR_TRANSCRIPTION_FAILED", f"Transcription failed: {str(e)}")
    else:
        return error_response("ERR_AUDIO_EMPTY", "No audio file, transcript text, or demo index provided.")

    if not transcript or not transcript.strip():
        return error_response("ERR_TRANSCRIPTION_FAILED", "Transcription produced empty text.")

    # ── Step 2: Sanitize transcript ──
    transcript, injection_flags = sanitize_transcript(transcript)

    # ── Step 3: Extract structured data ──
    try:
        extractor = get_extraction_provider(settings)
        extracted = extractor.extract(transcript)
    except ExtractionError as e:
        return error_response(e.code, e.message)
    except Exception as e:
        return error_response("ERR_EXTRACTION_FAILED", f"Extraction failed: {str(e)}")

    # Merge injection flags into extraction flags
    all_flags = list(set(extracted.flags + injection_flags))
    extracted.flags = all_flags

    # ── Step 4: Validate financial invariant ──
    validation = validate_financial_invariant(
        total_amount=extracted.financials.total_amount,
        cash_paid=extracted.financials.cash_paid,
        upi_paid=extracted.financials.upi_paid,
        credit_amount=extracted.financials.credit_amount,
    )

    # Add validation flags
    if validation.flags:
        all_flags.extend(validation.flags)

    # ── Step 5: Customer matching ──
    customer_match_result = match_customer(
        merchant_id=merchant_id,
        extracted_name=extracted.customer.name,
        extracted_phone=extracted.customer.phone,
        db=db,
    )

    # ── Step 6: Generate idempotency hash ──
    idempotency_hash = generate_idempotency_hash(merchant_id, transcript)

    # Check for existing duplicate
    existing = db.query(LedgerEntry).filter(
        LedgerEntry.idempotency_hash == idempotency_hash
    ).first()
    if existing:
        all_flags.append("ERR_DUPLICATE_TRANSACTION")

    # ── Step 7: Determine if safe to commit ──
    can_commit = (
        validation.valid
        and not injection_flags
        and "ERR_DUPLICATE_TRANSACTION" not in all_flags
        and not customer_match_result.is_ambiguous
        and not customer_match_result.is_new_customer
    )

    # If new customer, still allow commit (will create customer)
    if customer_match_result.is_new_customer and validation.valid and not injection_flags:
        can_commit = True

    return VoiceProcessResponse(
        transcript=transcript,
        draft=extracted,
        customer_match=customer_match_result,
        validation=validation,
        can_commit=can_commit,
        idempotency_hash=idempotency_hash,
        flags=all_flags,
    )


# ── Ledger Commit ──────────────────────────────────────────────────────────────

@app.post("/api/ledger/commit")
def ledger_commit(
    request: CommitRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Atomically commit a verified transaction to the ledger.

    NEVER trusts frontend validation — independently revalidates everything:
    1. Enforce merchant ownership
    2. Recalculate financial invariants
    3. Check idempotency
    4. Insert LedgerEntry + TransactionItems
    5. Update customer outstanding balance
    6. Generate PaymentRecovery if credit > 0
    7. Commit or rollback
    """
    settings = get_settings()

    # ── Verify and enforce authenticated merchant (strict tenant isolation) ──
    merchant = current_merchant
    request.merchant_id = current_merchant.id


    # ── Server-side financial revalidation (NEVER trust frontend) ──
    total = safe_decimal(request.total_amount)
    cash = safe_decimal(request.cash_paid)
    upi = safe_decimal(request.upi_paid)
    credit = safe_decimal(request.credit_amount)

    validation = validate_financial_invariant(total, cash, upi, credit)
    if not validation.valid:
        return error_response(
            validation.flag_code or "ERR_MATH_MISMATCH",
            validation.message or "Financial amounts do not balance.",
            details={
                "expected": str(cash + upi + credit),
                "actual": str(total),
                "delta": str(validation.delta),
            },
        )

    # ── Sanitize transcript ──
    _, injection_flags = sanitize_transcript(request.raw_transcript)
    if injection_flags:
        return error_response(
            "ERR_PROMPT_INJECTION",
            "Suspicious content detected in transcript.",
        )

    # ── Idempotency check ──
    existing = db.query(LedgerEntry).filter(
        LedgerEntry.idempotency_hash == request.idempotency_hash
    ).first()
    if existing:
        return error_response(
            "ERR_DUPLICATE_TRANSACTION",
            "This transaction has already been recorded.",
            details={"existing_entry_id": existing.id},
        )

    # ── Begin atomic transaction ──
    try:
        # Resolve or create customer
        customer = None
        if request.customer_id:
            customer = db.query(Customer).filter(
                Customer.id == request.customer_id,
                Customer.merchant_id == request.merchant_id,
            ).first()
            if not customer:
                return error_response("ERR_CUSTOMER_NOT_FOUND", "Customer not found.")

        if not customer and request.customer_name:
            # Create new customer
            customer = Customer(
                id=gen_uuid(),
                merchant_id=request.merchant_id,
                name=request.customer_name,
                phone=request.customer_phone,
                total_outstanding=Decimal("0.00"),
            )
            db.add(customer)
            db.flush()

        if not customer:
            return error_response("ERR_CUSTOMER_NOT_FOUND", "No customer specified or could be created.")

        # ── Parse due date ──
        due_date = None
        if request.due_date:
            try:
                due_date = datetime.fromisoformat(request.due_date).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        # ── Create LedgerEntry ──
        entry_id = gen_uuid()
        entry = LedgerEntry(
            id=entry_id,
            merchant_id=request.merchant_id,
            customer_id=customer.id,
            transaction_type=request.transaction_type.value,
            total_amount=total,
            cash_paid=cash,
            upi_paid=upi,
            credit_amount=credit,
            due_date=due_date,
            raw_transcript=request.raw_transcript,
            confidence_score=request.confidence_score,
            status="COMMITTED",
            idempotency_hash=request.idempotency_hash,
        )
        db.add(entry)

        # ── Create TransactionItems ──
        for item in request.items:
            db.add(TransactionItem(
                id=gen_uuid(),
                ledger_entry_id=entry_id,
                item_name=item.item_name,
                quantity=item.quantity,
                unit_price=safe_decimal(item.unit_price) if item.unit_price else None,
            ))

        # ── Update customer outstanding balance ──
        # SALE: outstanding += credit_amount
        # PAYMENT_RECEIVED: outstanding -= total_amount (payment reduces debt)
        if request.transaction_type.value == "SALE":
            if credit > Decimal("0"):
                new_outstanding = Decimal(str(customer.total_outstanding)) + credit
                customer.total_outstanding = new_outstanding
        elif request.transaction_type.value == "PAYMENT_RECEIVED":
            payment_amount = total
            current_outstanding = Decimal(str(customer.total_outstanding))
            if payment_amount > current_outstanding:
                # Payment exceeds outstanding — flag and reject
                db.rollback()
                return error_response(
                    "ERR_NEGATIVE_BALANCE",
                    "Payment would create a negative balance.",
                    details={
                        "current_outstanding": str(current_outstanding),
                        "payment_amount": str(payment_amount),
                    },
                )
            customer.total_outstanding = current_outstanding - payment_amount

        # ── Generate PaymentRecovery if credit > 0 ──
        recovery_id = None
        upi_deep_link = None

        if credit > Decimal("0"):
            upi_deep_link = generate_upi_deep_link(
                merchant_vpa=merchant.vpa_upi_id,
                merchant_name=merchant.business_name,
                amount=credit,
                transaction_reference=f"LEDGER-{entry_id[:8]}",
            )

            recovery_id = gen_uuid()
            recovery = PaymentRecovery(
                id=recovery_id,
                ledger_entry_id=entry_id,
                customer_id=customer.id,
                amount=credit,
                upi_deep_link=upi_deep_link,
                scheduled_reminder_date=due_date or datetime.now(timezone.utc) + timedelta(days=1),
                status="PENDING",
            )
            db.add(recovery)

        # ── Commit atomic transaction ──
        db.commit()

        return CommitResponse(
            success=True,
            ledger_entry_id=entry_id,
            customer_id=customer.id,
            customer_outstanding=customer.total_outstanding,
            recovery_id=recovery_id,
            upi_deep_link=upi_deep_link,
            message="Transaction recorded successfully. ✓",
        )

    except Exception as e:
        db.rollback()
        return error_response(
            "ERR_INVALID_TRANSACTION",
            f"Transaction failed: {str(e)}",
            status=500,
        )


# ── Ledger Summary ─────────────────────────────────────────────────────────────

@app.get("/api/ledger/summary", response_model=LedgerSummary)
def ledger_summary(
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Daily financial KPI summary for the dashboard.
    Strictly scoped to current_merchant to ensure no cross-user data leakage.

    Calculations:
    - total_sales: sum of total_amount for COMMITTED SALE entries today
    - cash_in_hand: sum of cash_paid for COMMITTED entries today
    - upi_collected: sum of upi_paid for COMMITTED entries today
    - total_credit_given: sum of credit_amount for COMMITTED SALE entries today
    - outstanding_udhaar: sum of all customer total_outstanding
    - overdue_recoveries: count of PENDING recoveries past scheduled date
    """
    merchant_id = current_merchant.id


    # Today's date range (UTC)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Aggregate today's committed entries
    result = db.query(
        func.coalesce(func.sum(
            case(
                (LedgerEntry.transaction_type == "SALE", LedgerEntry.total_amount),
                else_=0,
            )
        ), 0).label("total_sales"),
        func.coalesce(func.sum(LedgerEntry.cash_paid), 0).label("cash_in_hand"),
        func.coalesce(func.sum(LedgerEntry.upi_paid), 0).label("upi_collected"),
        func.coalesce(func.sum(
            case(
                (LedgerEntry.transaction_type == "SALE", LedgerEntry.credit_amount),
                else_=0,
            )
        ), 0).label("total_credit_given"),
    ).filter(
        LedgerEntry.merchant_id == merchant_id,
        LedgerEntry.status == "COMMITTED",
        LedgerEntry.created_at >= today_start,
        LedgerEntry.created_at < today_end,
    ).first()

    # Total outstanding across all customers
    outstanding = db.query(
        func.coalesce(func.sum(Customer.total_outstanding), 0)
    ).filter(
        Customer.merchant_id == merchant_id
    ).scalar()

    # Count overdue recoveries
    now = datetime.now(timezone.utc)
    overdue_count = db.query(func.count(PaymentRecovery.id)).join(
        LedgerEntry, PaymentRecovery.ledger_entry_id == LedgerEntry.id
    ).filter(
        LedgerEntry.merchant_id == merchant_id,
        PaymentRecovery.status == "PENDING",
        PaymentRecovery.scheduled_reminder_date < now,
    ).scalar() or 0

    return LedgerSummary(
        total_sales=Decimal(str(result.total_sales)) if result else Decimal("0"),
        cash_in_hand=Decimal(str(result.cash_in_hand)) if result else Decimal("0"),
        upi_collected=Decimal(str(result.upi_collected)) if result else Decimal("0"),
        total_credit_given=Decimal(str(result.total_credit_given)) if result else Decimal("0"),
        outstanding_udhaar=Decimal(str(outstanding)),
        overdue_recoveries=overdue_count,
    )


# ── Ledger Entries ─────────────────────────────────────────────────────────────

@app.get("/api/ledger/entries", response_model=PaginatedLedgerResponse)
def ledger_entries(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Paginated ledger history, newest first, strictly scoped to current_merchant."""
    merchant_id = current_merchant.id


    # Total count
    total = db.query(func.count(LedgerEntry.id)).filter(
        LedgerEntry.merchant_id == merchant_id,
        LedgerEntry.status == "COMMITTED",
    ).scalar() or 0

    # Paginated query
    entries = (
        db.query(LedgerEntry)
        .options(
            joinedload(LedgerEntry.customer),
            joinedload(LedgerEntry.items),
            joinedload(LedgerEntry.payment_recovery),
        )
        .filter(
            LedgerEntry.merchant_id == merchant_id,
            LedgerEntry.status == "COMMITTED",
        )
        .order_by(LedgerEntry.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    response_entries = []
    for entry in entries:
        recovery_resp = None
        if entry.payment_recovery:
            recovery_resp = PaymentRecoveryResponse(
                id=entry.payment_recovery.id,
                amount=entry.payment_recovery.amount,
                upi_deep_link=entry.payment_recovery.upi_deep_link,
                razorpay_link_id=entry.payment_recovery.razorpay_link_id,
                razorpay_short_url=entry.payment_recovery.razorpay_short_url,
                scheduled_reminder_date=(
                    entry.payment_recovery.scheduled_reminder_date.isoformat()
                    if entry.payment_recovery.scheduled_reminder_date else None
                ),
                status=entry.payment_recovery.status,
            )

        response_entries.append(LedgerEntryResponse(
            id=entry.id,
            merchant_id=entry.merchant_id,
            customer_id=entry.customer_id,
            customer_name=entry.customer.name if entry.customer else None,
            transaction_type=entry.transaction_type,
            total_amount=entry.total_amount,
            cash_paid=entry.cash_paid,
            upi_paid=entry.upi_paid,
            credit_amount=entry.credit_amount,
            due_date=entry.due_date.isoformat() if entry.due_date else None,
            raw_transcript=entry.raw_transcript,
            confidence_score=entry.confidence_score,
            status=entry.status,
            created_at=entry.created_at.isoformat() if entry.created_at else "",
            items=[
                TransactionItemResponse(
                    id=item.id,
                    item_name=item.item_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
                for item in entry.items
            ],
            recovery=recovery_resp,
        ))

    return PaginatedLedgerResponse(
        entries=response_entries,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=math.ceil(total / per_page) if total > 0 else 0,
    )


# ── Recovery & Razorpay Payment Rails ─────────────────────────────────────────

@app.post("/api/recovery/send-reminder")
def send_recovery_reminder(
    request: RecoveryReminderRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Generate a mock WhatsApp recovery reminder.
    Creates a valid WhatsApp click-to-chat URL with polite Hinglish message.
    Updates recovery status to LINK_SENT.
    """
    # Find recovery
    recovery = db.query(PaymentRecovery).filter(
        PaymentRecovery.id == request.recovery_id
    ).first()
    if not recovery:
        return error_response("ERR_RECOVERY_NOT_FOUND", "Recovery record not found.", status=404)

    # Verify merchant ownership
    entry = db.query(LedgerEntry).filter(
        LedgerEntry.id == recovery.ledger_entry_id,
        LedgerEntry.merchant_id == current_merchant.id,
    ).first()
    if not entry:
        return error_response("ERR_UNAUTHORIZED", "Recovery does not belong to your merchant account.", status=403)

    # Get customer
    customer = db.query(Customer).filter(
        Customer.id == recovery.customer_id,
        Customer.merchant_id == current_merchant.id,
    ).first()
    if not customer:
        return error_response("ERR_CUSTOMER_NOT_FOUND", "Customer not found.", status=404)

    # Get merchant
    merchant = current_merchant

    # Generate WhatsApp reminder
    reminder = generate_whatsapp_reminder(
        customer_name=customer.name,
        customer_phone=customer.phone,
        amount=recovery.amount,
        upi_link=recovery.razorpay_short_url or recovery.upi_deep_link or "",
        merchant_name=merchant.business_name if merchant else "Dukan",
    )

    # Update recovery status
    recovery.status = "LINK_SENT"
    db.commit()

    return RecoveryReminderResponse(
        success=True,
        whatsapp_url=reminder["whatsapp_url"],
        message=reminder["message"],
        recovery_status="LINK_SENT",
    )


@app.post("/api/recovery/razorpay-link", response_model=RazorpayLinkResponse)
def create_recovery_razorpay_link(
    request: RazorpayLinkCreateRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Generate an official Razorpay Payment Link and dynamic QR for outstanding Udhar recovery.
    Enables Kirana customers to pay via Razorpay UPI, Cards, Netbanking, or Wallets.
    """
    recovery = db.query(PaymentRecovery).filter(PaymentRecovery.id == request.recovery_id).first()
    if not recovery:
        return error_response("ERR_RECOVERY_NOT_FOUND", "Recovery record not found.", status=404)

    # Verify merchant ownership
    entry = db.query(LedgerEntry).filter(
        LedgerEntry.id == recovery.ledger_entry_id,
        LedgerEntry.merchant_id == current_merchant.id,
    ).first()
    if not entry:
        return error_response("ERR_UNAUTHORIZED", "Recovery does not belong to your merchant account.", status=403)

    customer = db.query(Customer).filter(Customer.id == recovery.customer_id).first()
    if not customer:
        return error_response("ERR_CUSTOMER_NOT_FOUND", "Customer not found.", status=404)

    amount = request.amount if request.amount is not None else recovery.amount
    link_info = create_razorpay_payment_link(
        amount=amount,
        customer_name=customer.name,
        customer_phone=customer.phone,
        recovery_id=recovery.id,
        merchant_name=current_merchant.business_name,
        merchant_vpa=current_merchant.vpa_upi_id,
    )

    # Persist link details on recovery
    recovery.razorpay_link_id = link_info["id"]
    recovery.razorpay_short_url = link_info["short_url"]
    recovery.payment_method = "RAZORPAY_LINK"
    db.commit()

    return RazorpayLinkResponse(
        recovery_id=recovery.id,
        razorpay_link_id=link_info["id"],
        short_url=link_info["short_url"],
        qr_code_url=link_info["qr_code_url"],
        upi_intent_url=link_info["upi_intent_url"],
        amount=amount,
        customer_name=customer.name,
        status="created",
    )


@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db),
):
    """
    Razorpay Webhook receiver with cryptographic HMAC SHA-256 signature verification.
    Automatically settles Udhar, logs a PAYMENT_RECEIVED entry, and zeros out dues.
    """
    body_bytes = await request.body()
    settings = get_settings()

    # Verify signature if webhook secret is configured and header is supplied
    if x_razorpay_signature:
        is_valid = verify_razorpay_webhook_signature(
            raw_body=body_bytes,
            signature=x_razorpay_signature,
            secret=settings.RAZORPAY_WEBHOOK_SECRET,
        )
        if not is_valid:
            return error_response("ERR_INVALID_SIGNATURE", "Invalid webhook HMAC signature.", status=400)

    try:
        data = await request.json()
    except Exception:
        return error_response("ERR_INVALID_JSON", "Failed to parse JSON webhook payload.", status=400)

    event = data.get("event")
    payload = data.get("payload", {})

    reconciliation_result = None
    if event in ["payment_link.paid", "payment.captured", "payment_link.partially_paid"]:
        payment_link = payload.get("payment_link", {}).get("entity", {})
        payment = payload.get("payment", {}).get("entity", {})

        link_id = payment_link.get("id")
        payment_id = payment.get("id") or f"pay_{uuid.uuid4().hex[:10]}"
        amount_paisa = payment.get("amount") or payment_link.get("amount_paid")
        amount = Decimal(str(amount_paisa / 100)) if amount_paisa else None

        recovery = None
        if link_id:
            recovery = db.query(PaymentRecovery).filter(PaymentRecovery.razorpay_link_id == link_id).first()

        if recovery:
            reconciliation_result = reconcile_recovery_payment(
                db=db,
                recovery_id=recovery.id,
                razorpay_payment_id=payment_id,
                amount_paid=amount,
            )

    return {
        "status": "ok",
        "event": event,
        "reconciled": reconciliation_result is not None,
        "details": reconciliation_result,
    }


@app.post("/api/recovery/simulate-razorpay-payment", response_model=SimulatePaymentResponse)
def simulate_razorpay_payment(
    request: SimulatePaymentRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    1-Click simulator for hackathon judges & merchants to test end-to-end Razorpay payment settlement.
    Atomically clears the customer's due, logs PAYMENT_RECEIVED in ledger, and updates recovery status.
    """
    recovery = db.query(PaymentRecovery).filter(PaymentRecovery.id == request.recovery_id).first()
    if not recovery:
        return error_response("ERR_RECOVERY_NOT_FOUND", "Recovery record not found.", status=404)

    # Verify merchant ownership
    entry = db.query(LedgerEntry).filter(
        LedgerEntry.id == recovery.ledger_entry_id,
        LedgerEntry.merchant_id == current_merchant.id,
    ).first()
    if not entry:
        return error_response("ERR_UNAUTHORIZED", "Recovery does not belong to your merchant account.", status=403)

    customer = db.query(Customer).filter(Customer.id == recovery.customer_id).first()
    if not customer:
        return error_response("ERR_CUSTOMER_NOT_FOUND", "Customer not found.", status=404)

    amount = request.amount if request.amount is not None else recovery.amount
    payment_id = f"pay_rzp_demo_{secrets.token_hex(4)}"

    result = reconcile_recovery_payment(
        db=db,
        recovery_id=recovery.id,
        razorpay_payment_id=payment_id,
        amount_paid=amount,
    )

    return SimulatePaymentResponse(
        success=True,
        message=f"Payment of ₹{result['amount_paid']} received via Razorpay for {customer.name}!",
        razorpay_payment_id=payment_id,
        recovery_id=recovery.id,
        customer_name=customer.name,
        amount_paid=result["amount_paid"],
        new_outstanding=result["new_outstanding"],
        recovery_status="COLLECTED",
    )


@app.post("/api/recovery/settle-payment", response_model=SettlePaymentResponse)
def settle_payment(
    request: SettlePaymentRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Directly record a payment (Cash, UPI, or Razorpay) for an existing customer due.
    Supports both full and partial payments.
    Updates customer balance, creates PAYMENT_RECEIVED ledger entry, and marks recovery as COLLECTED if fully paid.
    """
    customer = db.query(Customer).filter(
        Customer.id == request.customer_id,
        Customer.merchant_id == current_merchant.id,
    ).first()
    if not customer:
        return error_response("ERR_CUSTOMER_NOT_FOUND", "Customer not found.", status=404)

    amount = safe_decimal(request.amount)
    current_outstanding = Decimal(str(customer.total_outstanding))

    if amount > current_outstanding:
        return error_response(
            "ERR_NEGATIVE_BALANCE",
            f"Payment amount (₹{amount}) cannot exceed current outstanding due (₹{current_outstanding}).",
            status=400,
        )

    mode = (request.payment_mode or "CASH").upper()
    cash_paid = amount if mode == "CASH" else Decimal("0.00")
    upi_paid = amount if mode in ("UPI", "RAZORPAY") else Decimal("0.00")

    # Deduct from customer's outstanding balance
    new_outstanding = current_outstanding - amount
    customer.total_outstanding = new_outstanding

    # Create immutable PAYMENT_RECEIVED ledger entry
    entry_id = gen_uuid()
    idempotency_hash = generate_idempotency_hash(
        merchant_id=current_merchant.id,
        transcript=f"Settle {mode} {customer.id} {amount} {datetime.now(timezone.utc).isoformat()}",
    )

    ledger_entry = LedgerEntry(
        id=entry_id,
        merchant_id=current_merchant.id,
        customer_id=customer.id,
        transaction_type="PAYMENT_RECEIVED",
        total_amount=amount,
        cash_paid=cash_paid,
        upi_paid=upi_paid,
        credit_amount=Decimal("0.00"),
        raw_transcript=request.notes or f"Customer {customer.name} settled ₹{amount} via {mode}",
        confidence_score=1.0,
        status="COMMITTED",
        idempotency_hash=idempotency_hash,
    )
    db.add(ledger_entry)

    # If recovery_id provided or active recovery exists, update status
    recovery = None
    if request.recovery_id:
        recovery = db.query(PaymentRecovery).filter(
            PaymentRecovery.id == request.recovery_id,
        ).first()
    if not recovery:
        recovery = db.query(PaymentRecovery).filter(
            PaymentRecovery.customer_id == customer.id,
            PaymentRecovery.status.in_(["PENDING", "LINK_SENT"]),
        ).first()

    if recovery:
        if new_outstanding == Decimal("0.00"):
            recovery.status = "COLLECTED"
        else:
            recovery.amount = new_outstanding

    db.commit()

    mode_label = "Cash (रोकड़)" if mode == "CASH" else "UPI / Online"
    return SettlePaymentResponse(
        success=True,
        message=f"₹{amount} {mode_label} payment recorded for {customer.name}! Remaining balance: ₹{new_outstanding}.",
        entry_id=entry_id,
        amount_paid=amount,
        payment_mode=mode,
        remaining_balance=new_outstanding,
        customer_name=customer.name,
    )


# ── Customers with Dues ───────────────────────────────────────────────────────

@app.get("/api/customers/dues")
def customers_with_dues(
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Get all customers with outstanding balances for the recovery feed, strictly scoped to current_merchant."""
    merchant_id = current_merchant.id

    customers = (
        db.query(Customer)
        .filter(
            Customer.merchant_id == merchant_id,
            Customer.total_outstanding > 0,
        )
        .order_by(Customer.total_outstanding.desc())
        .all()
    )

    now = datetime.now(timezone.utc)
    result = []

    for c in customers:
        # Find latest recovery for this customer
        latest_recovery = (
            db.query(PaymentRecovery)
            .filter(PaymentRecovery.customer_id == c.id)
            .order_by(PaymentRecovery.created_at.desc())
            .first()
        )

        is_overdue = False
        recovery_id = None
        recovery_status = None
        upi_deep_link = None
        razorpay_link_id = None
        razorpay_short_url = None
        latest_due = None

        if latest_recovery:
            recovery_id = latest_recovery.id
            recovery_status = latest_recovery.status
            upi_deep_link = latest_recovery.upi_deep_link
            razorpay_link_id = latest_recovery.razorpay_link_id
            razorpay_short_url = latest_recovery.razorpay_short_url

            if latest_recovery.scheduled_reminder_date:
                latest_due = latest_recovery.scheduled_reminder_date.isoformat()
                # Normalize to offset-aware for comparison
                sched = latest_recovery.scheduled_reminder_date
                if sched.tzinfo is None:
                    sched = sched.replace(tzinfo=timezone.utc)
                is_overdue = sched < now

        result.append(CustomerWithDues(
            id=c.id,
            name=c.name,
            phone=c.phone,
            total_outstanding=c.total_outstanding,
            latest_due_date=latest_due,
            is_overdue=is_overdue,
            recovery_id=recovery_id,
            recovery_status=recovery_status,
            upi_deep_link=upi_deep_link,
            razorpay_link_id=razorpay_link_id,
            razorpay_short_url=razorpay_short_url,
        ).model_dump())

    return result


# ── Demo Seed ──────────────────────────────────────────────────────────────────

@app.post("/api/demo/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    """Load demo data for judging/demonstration purposes."""
    from backend.seed import seed_database
    try:
        result = seed_database(db)
        if result and result.get("seeded"):
            return {"success": True, "message": result["message"]}
        else:
            return {"success": True, "message": result["message"] if result else "Seed completed."}
    except Exception as e:
        return error_response("ERR_SEED_FAILED", f"Failed to load demo data: {str(e)}", status=500)
