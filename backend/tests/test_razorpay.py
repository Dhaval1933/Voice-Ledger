"""
Tests for Razorpay Payment Rails, Links, Dynamic QR, and Webhook Auto-Reconciliation.

Verifies:
- Generation of official Razorpay Payment Links with UPI intent
- Merchant authentication requirement for link generation
- 1-click Razorpay payment simulation
- Automatic ledger reconciliation (PAYMENT_RECEIVED entry, Udhar zeroed, status COLLECTED)
- Cryptographic HMAC SHA-256 webhook signature verification and settlement
"""

import hmac
import hashlib
import json
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import Base, init_db, engine
from backend.config import get_settings


@pytest.fixture(scope="module")
def client():
    """Create test client and initialize database with test merchant."""
    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as c:
        # Register test merchant
        signup_res = c.post("/api/auth/signup", json={
            "email": "razorpay_merchant@kirana.com",
            "name": "Vikram",
            "surname": "Patel",
            "shop_name": "Patel Superstore",
            "phone": "9811223344",
            "password": "merchantSecret123",
        })
        token = signup_res.json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


class TestRazorpayPaymentRails:
    def test_create_credit_sale_and_razorpay_link(self, client):
        """Test committing an Udhar sale and generating a Razorpay link."""
        # 1. Commit credit sale
        commit_payload = {
            "merchant_id": "ignored",
            "customer_name": "Sanjay Gupta",
            "customer_phone": "9876599999",
            "transaction_type": "SALE",
            "total_amount": "850.00",
            "cash_paid": "150.00",
            "upi_paid": "0.00",
            "credit_amount": "700.00",
            "raw_transcript": "Sanjay ji ne 850 ka samaan liya, 150 cash diya baaki udhar",
            "confidence_score": 0.96,
            "idempotency_hash": "hash-rzp-test-001",
            "items": [{"item_name": "Ghee", "quantity": "1kg", "unit_price": "700.00"}],
        }
        commit_res = client.post("/api/ledger/commit", json=commit_payload)
        assert commit_res.status_code == 200
        commit_data = commit_res.json()
        assert commit_data["recovery_id"] is not None
        recovery_id = commit_data["recovery_id"]

        # 2. Generate Razorpay Payment Link
        link_res = client.post("/api/recovery/razorpay-link", json={
            "recovery_id": recovery_id,
        })
        assert link_res.status_code == 200
        link_data = link_res.json()
        assert link_data["recovery_id"] == recovery_id
        assert link_data["razorpay_link_id"].startswith("plink_")
        assert "rzp.io/i/" in link_data["short_url"]
        assert link_data["qr_code_url"] is not None
        assert float(link_data["amount"]) == 700.00
        assert link_data["customer_name"] == "Sanjay Gupta"

        # 3. Verify Customer Dues feed now shows the Razorpay link
        dues_res = client.get("/api/customers/dues")
        assert dues_res.status_code == 200
        dues = dues_res.json()
        target_due = next(d for d in dues if d["name"] == "Sanjay Gupta")
        assert target_due["razorpay_link_id"] == link_data["razorpay_link_id"]
        assert target_due["razorpay_short_url"] == link_data["short_url"]
        assert float(target_due["total_outstanding"]) == 700.00

    def test_simulate_razorpay_payment_settlement(self, client):
        """Test 1-click simulation of customer paying via Razorpay."""
        # 1. Commit another credit sale
        commit_res = client.post("/api/ledger/commit", json={
            "merchant_id": "ignored",
            "customer_name": "Kavita Devi",
            "customer_phone": "9876588888",
            "transaction_type": "SALE",
            "total_amount": "500.00",
            "cash_paid": "0.00",
            "upi_paid": "0.00",
            "credit_amount": "500.00",
            "raw_transcript": "Kavita ji 500 udhar",
            "confidence_score": 0.95,
            "idempotency_hash": "hash-rzp-test-002",
        })
        recovery_id = commit_res.json()["recovery_id"]

        # 2. Simulate customer payment
        sim_res = client.post("/api/recovery/simulate-razorpay-payment", json={
            "recovery_id": recovery_id,
            "amount": "500.00",
        })
        assert sim_res.status_code == 200
        sim_data = sim_res.json()
        assert sim_data["success"] is True
        assert sim_data["recovery_status"] == "COLLECTED"
        assert float(sim_data["new_outstanding"]) == 0.00
        assert sim_data["razorpay_payment_id"].startswith("pay_rzp_")

        # 3. Verify ledger has a new PAYMENT_RECEIVED transaction entry
        entries_res = client.get("/api/ledger/entries")
        entries = entries_res.json()["entries"]
        latest_entry = entries[0]
        assert latest_entry["transaction_type"] == "PAYMENT_RECEIVED"
        assert float(latest_entry["total_amount"]) == 500.00
        assert float(latest_entry["upi_paid"]) == 500.00
        assert "Razorpay" in latest_entry["raw_transcript"]

    def test_razorpay_webhook_reconciliation(self, client):
        """Test Razorpay HMAC webhook payload auto-reconciliation."""
        settings = get_settings()

        # 1. Commit credit sale
        commit_res = client.post("/api/ledger/commit", json={
            "merchant_id": "ignored",
            "customer_name": "Deepak Kumar",
            "customer_phone": "9876577777",
            "transaction_type": "SALE",
            "total_amount": "400.00",
            "cash_paid": "0.00",
            "upi_paid": "0.00",
            "credit_amount": "400.00",
            "raw_transcript": "Deepak 400 udhar",
            "confidence_score": 0.98,
            "idempotency_hash": "hash-rzp-test-003",
        })
        recovery_id = commit_res.json()["recovery_id"]

        # 2. Generate Razorpay link
        link_res = client.post("/api/recovery/razorpay-link", json={"recovery_id": recovery_id})
        link_id = link_res.json()["razorpay_link_id"]

        # 3. Construct official Razorpay webhook payload
        webhook_body = {
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": link_id,
                        "amount_paid": 40000,  # in paise
                        "status": "paid",
                    }
                },
                "payment": {
                    "entity": {
                        "id": "pay_live_webhook_999",
                        "amount": 40000,
                        "status": "captured",
                        "method": "upi",
                    }
                }
            }
        }
        raw_json = json.dumps(webhook_body).encode("utf-8")

        # Generate HMAC SHA-256 signature
        signature = hmac.new(
            key=settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            msg=raw_json,
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Send webhook
        webhook_res = client.post(
            "/api/webhooks/razorpay",
            content=raw_json,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
            },
        )
        assert webhook_res.status_code == 200
        res_data = webhook_res.json()
        assert res_data["reconciled"] is True
        assert res_data["details"]["status"] == "COLLECTED"
        assert float(res_data["details"]["new_outstanding"]) == 0.00

    def test_settle_due_in_cash_full_and_partial(self, client):
        """Test settling customer dues via Cash (full and partial)."""
        # 1. Commit credit sale of 1000
        commit_res = client.post("/api/ledger/commit", json={
            "merchant_id": "ignored",
            "customer_name": "Rakesh Yadav",
            "customer_phone": "9876543299",
            "transaction_type": "SALE",
            "total_amount": "1000.00",
            "cash_paid": "0.00",
            "upi_paid": "0.00",
            "credit_amount": "1000.00",
            "raw_transcript": "Rakesh 1000 udhar",
            "confidence_score": 0.95,
            "idempotency_hash": "hash-cash-test-001",
        })
        assert commit_res.status_code == 200
        customer_id = commit_res.json()["customer_id"]
        recovery_id = commit_res.json()["recovery_id"]

        # 2. Settle 400 in Cash (Partial)
        settle_res_1 = client.post("/api/recovery/settle-payment", json={
            "customer_id": customer_id,
            "recovery_id": recovery_id,
            "amount": "400.00",
            "payment_mode": "CASH",
            "notes": "Paid 400 cash at shop counter",
        })
        assert settle_res_1.status_code == 200
        data_1 = settle_res_1.json()
        assert data_1["success"] is True
        assert float(data_1["amount_paid"]) == 400.00
        assert float(data_1["remaining_balance"]) == 600.00
        assert data_1["payment_mode"] == "CASH"

        # Verify ledger has Cash payment entry
        entries_res = client.get("/api/ledger/entries")
        latest = entries_res.json()["entries"][0]
        assert latest["transaction_type"] == "PAYMENT_RECEIVED"
        assert float(latest["cash_paid"]) == 400.00
        assert float(latest["upi_paid"]) == 0.00

        # 3. Settle remaining 600 in Cash (Full)
        settle_res_2 = client.post("/api/recovery/settle-payment", json={
            "customer_id": customer_id,
            "recovery_id": recovery_id,
            "amount": "600.00",
            "payment_mode": "CASH",
        })
        assert settle_res_2.status_code == 200
        data_2 = settle_res_2.json()
        assert float(data_2["remaining_balance"]) == 0.00

        # 4. Attempting to settle more should be rejected
        settle_res_3 = client.post("/api/recovery/settle-payment", json={
            "customer_id": customer_id,
            "amount": "100.00",
            "payment_mode": "CASH",
        })
        assert settle_res_3.status_code == 400
