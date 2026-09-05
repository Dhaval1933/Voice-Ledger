"""
SQLAlchemy ORM models for the Voice Ledger.

All monetary fields use Numeric(12, 2) with database-level CHECK >= 0 constraints.
Customer outstanding balance is constrained to never go negative.
LedgerEntry idempotency_hash is unique to prevent duplicate transactions.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Numeric, Float, Text, Boolean,
    CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from backend.database import Base


def gen_uuid() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Generate timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    shop_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    merchants = relationship("Merchant", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    business_name = Column(String(255), nullable=False)
    vpa_upi_id = Column(String(320), nullable=False)
    phone = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="merchants")
    customers = relationship("Customer", back_populates="merchant", cascade="all, delete-orphan")
    ledger_entries = relationship("LedgerEntry", back_populates="merchant", cascade="all, delete-orphan")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    merchant_id = Column(String(36), ForeignKey("merchants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(15), nullable=True)
    total_outstanding = Column(
        Numeric(12, 2), nullable=False, default=0.00,
    )
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # DB-level constraint: outstanding can never be negative
    __table_args__ = (
        CheckConstraint("total_outstanding >= 0", name="ck_customer_outstanding_non_negative"),
        Index("ix_customer_merchant_name", "merchant_id", "name"),
    )

    # Relationships
    merchant = relationship("Merchant", back_populates="customers")
    ledger_entries = relationship("LedgerEntry", back_populates="customer")
    payment_recoveries = relationship("PaymentRecovery", back_populates="customer")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    merchant_id = Column(String(36), ForeignKey("merchants.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)

    # Transaction classification
    transaction_type = Column(String(20), nullable=False)  # SALE, PAYMENT_RECEIVED, EXPENSE, PURCHASE

    # Financial fields — all Decimal, all >= 0
    total_amount = Column(Numeric(12, 2), nullable=False)
    cash_paid = Column(Numeric(12, 2), nullable=False, default=0)
    upi_paid = Column(Numeric(12, 2), nullable=False, default=0)
    credit_amount = Column(Numeric(12, 2), nullable=False, default=0)

    due_date = Column(DateTime(timezone=True), nullable=True)
    raw_transcript = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # COMMITTED, FLAGGED, VOID
    status = Column(String(20), nullable=False, default="COMMITTED")

    # SHA-256 hash for duplicate prevention
    idempotency_hash = Column(String(64), nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_ledger_total_non_negative"),
        CheckConstraint("cash_paid >= 0", name="ck_ledger_cash_non_negative"),
        CheckConstraint("upi_paid >= 0", name="ck_ledger_upi_non_negative"),
        CheckConstraint("credit_amount >= 0", name="ck_ledger_credit_non_negative"),
        UniqueConstraint("idempotency_hash", name="uq_ledger_idempotency"),
        Index("ix_ledger_merchant_created", "merchant_id", "created_at"),
    )

    # Relationships
    merchant = relationship("Merchant", back_populates="ledger_entries")
    customer = relationship("Customer", back_populates="ledger_entries")
    items = relationship("TransactionItem", back_populates="ledger_entry", cascade="all, delete-orphan")
    payment_recovery = relationship("PaymentRecovery", back_populates="ledger_entry", uselist=False)


class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    ledger_entry_id = Column(String(36), ForeignKey("ledger_entries.id"), nullable=False)
    item_name = Column(String(255), nullable=False)
    quantity = Column(String(50), nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True)

    # Relationships
    ledger_entry = relationship("LedgerEntry", back_populates="items")


class PaymentRecovery(Base):
    __tablename__ = "payment_recoveries"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    ledger_entry_id = Column(String(36), ForeignKey("ledger_entries.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    upi_deep_link = Column(Text, nullable=True)
    razorpay_link_id = Column(String(100), nullable=True, index=True)
    razorpay_short_url = Column(String(255), nullable=True)
    razorpay_payment_id = Column(String(100), nullable=True)
    payment_method = Column(String(50), nullable=True, default="UPI")  # UPI, RAZORPAY_LINK
    scheduled_reminder_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING, LINK_SENT, COLLECTED
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_recovery_amount_non_negative"),
    )

    # Relationships
    ledger_entry = relationship("LedgerEntry", back_populates="payment_recovery")
    customer = relationship("Customer", back_populates="payment_recoveries")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    code = Column(String(6), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_reset_token_user_used", "user_id", "used"),
    )

    # Relationships
    user = relationship("User", back_populates="reset_tokens")
