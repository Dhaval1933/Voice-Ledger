"""
Seed data for the Voice Ledger.

Creates realistic demo data for judging/demonstration:
- 1 merchant (Demo Kirana Store)
- 5 customers with Hindi names
- 7+ ledger entries with varied payment splits
- Outstanding Udhar balances
- Pending and overdue recoveries

Usage:
    python -m backend.seed

Idempotent: checks if demo merchant already exists before seeding.
"""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import SessionLocal, init_db
from backend.models import (
    Customer, LedgerEntry, Merchant, PaymentRecovery, TransactionItem, User, gen_uuid,
)
from backend.auth import hash_password
from backend.services.recovery import generate_upi_deep_link
from backend.validator import generate_idempotency_hash


def seed_database(db: Session = None):
    """Seed the database with demo data."""
    close_session = False
    if db is None:
        init_db()
        db = SessionLocal()
        close_session = True

    settings = get_settings()
    merchant_id = settings.DEMO_MERCHANT_ID

    try:
        # Check if demo user already exists
        demo_user = db.query(User).filter(User.email == "demo@kirana.store").first()
        if not demo_user:
            demo_user = User(
                id=gen_uuid(),
                email="demo@kirana.store",
                name="Sharma",
                surname="Ji",
                shop_name="Sharma Kirana Store",
                phone="9876543210",
                password_hash=hash_password("sharma123"),
            )
            db.add(demo_user)
            db.flush()

        # Check if already seeded
        existing = db.query(Merchant).filter(Merchant.id == merchant_id).first()
        if existing:
            if not existing.user_id:
                existing.user_id = demo_user.id
                db.commit()
            print("Demo data already exists. Skipping seed.")
            return {"seeded": False, "message": "Demo data already exists. Skipping seed."}

        now = datetime.now(timezone.utc)

        # ── Create Merchant ──
        merchant = Merchant(
            id=merchant_id,
            user_id=demo_user.id,
            business_name="Sharma Kirana Store",
            vpa_upi_id="sharmakirana@upi",
            phone="9876543210",
        )
        db.add(merchant)
        db.flush()

        # ── Create Customers ──
        customers = {}
        customer_data = [
            ("Sharma ji", "9876501001", Decimal("250.00")),
            ("Ramesh bhai", "9876501002", Decimal("0.00")),
            ("Sita ji", "9876501003", Decimal("300.00")),
            ("Mohan", "9876501004", Decimal("600.00")),
            ("Gupta ji", "9876501005", Decimal("0.00")),
        ]

        for name, phone, outstanding in customer_data:
            cid = gen_uuid()
            customer = Customer(
                id=cid,
                merchant_id=merchant_id,
                name=name,
                phone=phone,
                total_outstanding=outstanding,
            )
            db.add(customer)
            customers[name] = customer
            db.flush()

        # ── Create Ledger Entries ──

        # Entry 1: Sharma ji — ₹450 sale, ₹200 cash, ₹250 udhar (kal)
        e1_id = gen_uuid()
        e1_hash = generate_idempotency_hash(
            merchant_id,
            "Sharma ji ne 450 ka rashan liya, 200 cash diya baaki kal denge.",
            now - timedelta(hours=3),
        )
        db.add(LedgerEntry(
            id=e1_id,
            merchant_id=merchant_id,
            customer_id=customers["Sharma ji"].id,
            transaction_type="SALE",
            total_amount=Decimal("450.00"),
            cash_paid=Decimal("200.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("250.00"),
            due_date=now + timedelta(days=1),
            raw_transcript="Sharma ji ne 450 ka rashan liya, 200 cash diya baaki kal denge.",
            confidence_score=0.92,
            status="COMMITTED",
            idempotency_hash=e1_hash,
            created_at=now - timedelta(hours=3),
        ))
        db.add(TransactionItem(id=gen_uuid(), ledger_entry_id=e1_id, item_name="rashan", quantity=None, unit_price=Decimal("450.00")))
        # Recovery for Sharma ji
        db.add(PaymentRecovery(
            id=gen_uuid(),
            ledger_entry_id=e1_id,
            customer_id=customers["Sharma ji"].id,
            amount=Decimal("250.00"),
            upi_deep_link=generate_upi_deep_link("sharmakirana@upi", "Sharma Kirana Store", Decimal("250.00"), f"LEDGER-{e1_id[:8]}"),
            scheduled_reminder_date=now + timedelta(days=1),
            status="PENDING",
        ))

        # Entry 2: Ramesh bhai — ₹1200 sale, pura UPI
        e2_id = gen_uuid()
        e2_hash = generate_idempotency_hash(
            merchant_id,
            "Ramesh bhai ne 1200 ka saman liya, pura UPI kar diya.",
            now - timedelta(hours=2),
        )
        db.add(LedgerEntry(
            id=e2_id,
            merchant_id=merchant_id,
            customer_id=customers["Ramesh bhai"].id,
            transaction_type="SALE",
            total_amount=Decimal("1200.00"),
            cash_paid=Decimal("0.00"),
            upi_paid=Decimal("1200.00"),
            credit_amount=Decimal("0.00"),
            raw_transcript="Ramesh bhai ne 1200 ka saman liya, pura UPI kar diya.",
            confidence_score=0.95,
            status="COMMITTED",
            idempotency_hash=e2_hash,
            created_at=now - timedelta(hours=2),
        ))
        db.add(TransactionItem(id=gen_uuid(), ledger_entry_id=e2_id, item_name="saman", quantity=None, unit_price=Decimal("1200.00")))

        # Entry 3: Sita ji — Payment received ₹500 cash against ₹800 old udhar
        e3_id = gen_uuid()
        e3_hash = generate_idempotency_hash(
            merchant_id,
            "Sita ji ka purana udhar 800 tha, 500 cash de diya.",
            now - timedelta(hours=1, minutes=30),
        )
        db.add(LedgerEntry(
            id=e3_id,
            merchant_id=merchant_id,
            customer_id=customers["Sita ji"].id,
            transaction_type="PAYMENT_RECEIVED",
            total_amount=Decimal("500.00"),
            cash_paid=Decimal("500.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("0.00"),
            raw_transcript="Sita ji ka purana udhar 800 tha, 500 cash de diya.",
            confidence_score=0.88,
            status="COMMITTED",
            idempotency_hash=e3_hash,
            created_at=now - timedelta(hours=1, minutes=30),
        ))
        # Sita ji still has ₹300 outstanding (800 - 500)
        db.add(PaymentRecovery(
            id=gen_uuid(),
            ledger_entry_id=e3_id,
            customer_id=customers["Sita ji"].id,
            amount=Decimal("300.00"),
            upi_deep_link=generate_upi_deep_link("sharmakirana@upi", "Sharma Kirana Store", Decimal("300.00"), f"LEDGER-{e3_id[:8]}"),
            scheduled_reminder_date=now - timedelta(days=1),  # OVERDUE
            status="PENDING",
        ))

        # Entry 4: Mohan — ₹600 sale, pura udhar
        e4_id = gen_uuid()
        e4_hash = generate_idempotency_hash(
            merchant_id,
            "Mohan ne 600 ka kirana liya, pura udhar likh do.",
            now - timedelta(hours=1),
        )
        db.add(LedgerEntry(
            id=e4_id,
            merchant_id=merchant_id,
            customer_id=customers["Mohan"].id,
            transaction_type="SALE",
            total_amount=Decimal("600.00"),
            cash_paid=Decimal("0.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("600.00"),
            raw_transcript="Mohan ne 600 ka kirana liya, pura udhar likh do.",
            confidence_score=0.91,
            status="COMMITTED",
            idempotency_hash=e4_hash,
            created_at=now - timedelta(hours=1),
        ))
        db.add(TransactionItem(id=gen_uuid(), ledger_entry_id=e4_id, item_name="kirana", quantity=None, unit_price=Decimal("600.00")))
        db.add(PaymentRecovery(
            id=gen_uuid(),
            ledger_entry_id=e4_id,
            customer_id=customers["Mohan"].id,
            amount=Decimal("600.00"),
            upi_deep_link=generate_upi_deep_link("sharmakirana@upi", "Sharma Kirana Store", Decimal("600.00"), f"LEDGER-{e4_id[:8]}"),
            scheduled_reminder_date=now + timedelta(days=2),
            status="PENDING",
        ))

        # Entry 5: Gupta ji — ₹950 sale, ₹450 cash + ₹500 UPI (fully paid)
        e5_id = gen_uuid()
        e5_hash = generate_idempotency_hash(
            merchant_id,
            "Gupta ji ne 950 ka maal liya, 450 cash aur 500 UPI kiya.",
            now - timedelta(minutes=30),
        )
        db.add(LedgerEntry(
            id=e5_id,
            merchant_id=merchant_id,
            customer_id=customers["Gupta ji"].id,
            transaction_type="SALE",
            total_amount=Decimal("950.00"),
            cash_paid=Decimal("450.00"),
            upi_paid=Decimal("500.00"),
            credit_amount=Decimal("0.00"),
            raw_transcript="Gupta ji ne 950 ka maal liya, 450 cash aur 500 UPI kiya.",
            confidence_score=0.94,
            status="COMMITTED",
            idempotency_hash=e5_hash,
            created_at=now - timedelta(minutes=30),
        ))
        db.add(TransactionItem(id=gen_uuid(), ledger_entry_id=e5_id, item_name="maal", quantity=None, unit_price=Decimal("950.00")))

        # Entry 6: Additional sale for Sita ji — ₹400, cash ₹100, udhar ₹300
        # (this contributes to her ₹300 outstanding shown above — total was ₹800, paid ₹500 in entry 3)
        # Actually her outstanding is already seeded at ₹300 in customer_data

        # Entry 7: Sharma ji older entry — already cleared
        e7_id = gen_uuid()
        e7_hash = generate_idempotency_hash(
            merchant_id,
            "Sharma ji ne 200 ka tel liya, pura cash diya.",
            now - timedelta(days=1),
        )
        db.add(LedgerEntry(
            id=e7_id,
            merchant_id=merchant_id,
            customer_id=customers["Sharma ji"].id,
            transaction_type="SALE",
            total_amount=Decimal("200.00"),
            cash_paid=Decimal("200.00"),
            upi_paid=Decimal("0.00"),
            credit_amount=Decimal("0.00"),
            raw_transcript="Sharma ji ne 200 ka tel liya, pura cash diya.",
            confidence_score=0.93,
            status="COMMITTED",
            idempotency_hash=e7_hash,
            created_at=now - timedelta(days=1),
        ))
        db.add(TransactionItem(id=gen_uuid(), ledger_entry_id=e7_id, item_name="tel", quantity="1L", unit_price=Decimal("200.00")))

        db.commit()
        print("[OK] Demo data seeded successfully!")
        print(f"   Merchant: Sharma Kirana Store (ID: {merchant_id})")
        print(f"   Customers: {len(customers)}")
        print(f"   Ledger entries: 6")
        print(f"   Outstanding Udhar: Sharma ji 250, Sita ji 300, Mohan 600")
        return {"seeded": True, "message": "Demo data loaded successfully! 🎉"}

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Seed failed: {e}")
        raise
    finally:
        if close_session:
            db.close()


if __name__ == "__main__":
    seed_database()
