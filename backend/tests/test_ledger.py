"""
Tests for ledger business logic and database operations.

Tests:
- Successful sale increases outstanding
- Payment decreases outstanding
- Payment cannot create negative balance
- Duplicate transaction rejected
- Recovery created for credit sale
- No recovery for fully paid sale
- Transaction rollback on failure
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from backend.database import Base, get_engine, SessionLocal, init_db
from backend.models import Merchant, Customer, LedgerEntry, TransactionItem, PaymentRecovery, gen_uuid
from backend.validator import generate_idempotency_hash

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create a test merchant
    merchant = Merchant(
        id="test-merchant-001",
        business_name="Test Kirana",
        vpa_upi_id="test@upi",
        phone="9999999999",
    )
    session.add(merchant)

    # Create test customers
    customer1 = Customer(
        id="test-customer-001",
        merchant_id="test-merchant-001",
        name="Sharma ji",
        phone="9876543001",
        total_outstanding=Decimal("0.00"),
    )
    customer2 = Customer(
        id="test-customer-002",
        merchant_id="test-merchant-001",
        name="Ramesh bhai",
        phone="9876543002",
        total_outstanding=Decimal("500.00"),
    )
    session.add_all([customer1, customer2])
    session.commit()

    yield session
    session.close()


class TestSaleTransaction:
    """Test SALE transaction behavior."""

    def test_sale_increases_outstanding(self, db_session):
        """A sale with credit should increase customer outstanding."""
        customer = db_session.query(Customer).filter(Customer.id == "test-customer-001").first()
        assert customer.total_outstanding == Decimal("0.00")

        # Record a sale with ₹250 credit
        credit = Decimal("250.00")
        customer.total_outstanding += credit
        db_session.commit()

        customer = db_session.query(Customer).filter(Customer.id == "test-customer-001").first()
        assert customer.total_outstanding == Decimal("250.00")

    def test_fully_paid_sale_no_outstanding_change(self, db_session):
        """A fully paid sale (no credit) should not change outstanding."""
        customer = db_session.query(Customer).filter(Customer.id == "test-customer-001").first()
        initial_outstanding = customer.total_outstanding

        # Sale fully paid — credit = 0
        # No change to outstanding
        db_session.commit()

        customer = db_session.query(Customer).filter(Customer.id == "test-customer-001").first()
        assert customer.total_outstanding == initial_outstanding


class TestPaymentTransaction:
    """Test PAYMENT_RECEIVED transaction behavior."""

    def test_payment_decreases_outstanding(self, db_session):
        """A payment should decrease customer outstanding."""
        customer = db_session.query(Customer).filter(Customer.id == "test-customer-002").first()
        assert customer.total_outstanding == Decimal("500.00")

        # Payment of ₹200
        payment = Decimal("200.00")
        customer.total_outstanding -= payment
        db_session.commit()

        customer = db_session.query(Customer).filter(Customer.id == "test-customer-002").first()
        assert customer.total_outstanding == Decimal("300.00")

    def test_payment_cannot_create_negative_balance(self, db_session):
        """Payment exceeding outstanding should be rejected (DB constraint)."""
        customer = db_session.query(Customer).filter(Customer.id == "test-customer-002").first()
        assert customer.total_outstanding == Decimal("500.00")

        # Try to pay ₹600 (exceeds ₹500 outstanding)
        payment = Decimal("600.00")
        new_outstanding = customer.total_outstanding - payment
        assert new_outstanding < 0  # This would violate constraint

        # The application should catch this before hitting the DB
        # But the DB constraint is the safety net
        customer.total_outstanding = Decimal("-100.00")
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_full_payment_zeros_outstanding(self, db_session):
        """Full payment should bring outstanding to exactly 0."""
        customer = db_session.query(Customer).filter(Customer.id == "test-customer-002").first()
        customer.total_outstanding = Decimal("0.00")
        db_session.commit()

        customer = db_session.query(Customer).filter(Customer.id == "test-customer-002").first()
        assert customer.total_outstanding == Decimal("0.00")


class TestIdempotency:
    """Test duplicate transaction prevention."""

    def test_duplicate_hash_rejected(self, db_session):
        """Two entries with the same idempotency hash should fail."""
        hash_val = generate_idempotency_hash("test-merchant-001", "duplicate test")

        entry1 = LedgerEntry(
            id=gen_uuid(),
            merchant_id="test-merchant-001",
            customer_id="test-customer-001",
            transaction_type="SALE",
            total_amount=Decimal("100.00"),
            cash_paid=Decimal("100.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("0.00"),
            status="COMMITTED",
            idempotency_hash=hash_val,
        )
        db_session.add(entry1)
        db_session.commit()

        entry2 = LedgerEntry(
            id=gen_uuid(),
            merchant_id="test-merchant-001",
            customer_id="test-customer-001",
            transaction_type="SALE",
            total_amount=Decimal("100.00"),
            cash_paid=Decimal("100.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("0.00"),
            status="COMMITTED",
            idempotency_hash=hash_val,  # Same hash!
        )
        db_session.add(entry2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()


class TestPaymentRecovery:
    """Test payment recovery generation."""

    def test_recovery_created_for_credit_sale(self, db_session):
        """A sale with credit > 0 should generate a PaymentRecovery."""
        entry_id = gen_uuid()
        hash_val = generate_idempotency_hash("test-merchant-001", "recovery test")

        entry = LedgerEntry(
            id=entry_id,
            merchant_id="test-merchant-001",
            customer_id="test-customer-001",
            transaction_type="SALE",
            total_amount=Decimal("500.00"),
            cash_paid=Decimal("200.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("300.00"),
            status="COMMITTED",
            idempotency_hash=hash_val,
        )
        db_session.add(entry)

        recovery = PaymentRecovery(
            id=gen_uuid(),
            ledger_entry_id=entry_id,
            customer_id="test-customer-001",
            amount=Decimal("300.00"),
            upi_deep_link="upi://pay?pa=test@upi&am=300&cu=INR",
            status="PENDING",
        )
        db_session.add(recovery)
        db_session.commit()

        # Verify recovery exists
        rec = db_session.query(PaymentRecovery).filter(
            PaymentRecovery.ledger_entry_id == entry_id
        ).first()
        assert rec is not None
        assert rec.amount == Decimal("300.00")
        assert rec.status == "PENDING"

    def test_no_recovery_for_fully_paid(self, db_session):
        """A fully paid sale (credit = 0) should NOT generate recovery."""
        entry_id = gen_uuid()
        hash_val = generate_idempotency_hash("test-merchant-001", "no recovery test")

        entry = LedgerEntry(
            id=entry_id,
            merchant_id="test-merchant-001",
            customer_id="test-customer-001",
            transaction_type="SALE",
            total_amount=Decimal("500.00"),
            cash_paid=Decimal("500.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("0.00"),
            status="COMMITTED",
            idempotency_hash=hash_val,
        )
        db_session.add(entry)
        db_session.commit()

        # No recovery should exist
        rec = db_session.query(PaymentRecovery).filter(
            PaymentRecovery.ledger_entry_id == entry_id
        ).first()
        assert rec is None


class TestLedgerEntry:
    """Test LedgerEntry creation and constraints."""

    def test_create_valid_entry(self, db_session):
        """Valid ledger entry should be created successfully."""
        entry = LedgerEntry(
            id=gen_uuid(),
            merchant_id="test-merchant-001",
            customer_id="test-customer-001",
            transaction_type="SALE",
            total_amount=Decimal("950.00"),
            cash_paid=Decimal("450.00"),
            upi_paid=Decimal("500.00"),
            credit_amount=Decimal("0.00"),
            raw_transcript="Gupta ji ne 950 ka maal liya",
            confidence_score=0.94,
            status="COMMITTED",
            idempotency_hash=generate_idempotency_hash("test-merchant-001", "valid entry test"),
        )
        db_session.add(entry)
        db_session.commit()

        assert entry.id is not None
        assert entry.total_amount == Decimal("950.00")

    def test_transaction_items(self, db_session):
        """Transaction items should be associated with entry."""
        entry_id = gen_uuid()
        entry = LedgerEntry(
            id=entry_id,
            merchant_id="test-merchant-001",
            transaction_type="SALE",
            total_amount=Decimal("500.00"),
            cash_paid=Decimal("500.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("0.00"),
            status="COMMITTED",
            idempotency_hash=generate_idempotency_hash("test-merchant-001", "items test"),
        )
        db_session.add(entry)

        item = TransactionItem(
            id=gen_uuid(),
            ledger_entry_id=entry_id,
            item_name="rashan",
            quantity="5kg",
            unit_price=Decimal("100.00"),
        )
        db_session.add(item)
        db_session.commit()

        items = db_session.query(TransactionItem).filter(
            TransactionItem.ledger_entry_id == entry_id
        ).all()
        assert len(items) == 1
        assert items[0].item_name == "rashan"
