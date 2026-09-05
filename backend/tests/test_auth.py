"""
Tests for authentication, authorization, password management, and data isolation.

Tests:
- User registration (Sign Up) with unique email, name, surname, shop_name, phone, password
- Duplicate email rejection
- Weak password rejection
- Login with bcrypt password verification
- Login failure with incorrect password
- Change password with old password verification and re-login with new password
- Strict multi-tenant data isolation between different shopkeepers
- Unauthenticated access rejection (401)
"""

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import Base, init_db, engine


@pytest.fixture(scope="module")
def client():
    """Create test client and initialize database."""
    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as c:
        yield c


class TestAuthEndpoints:
    def test_signup_success(self, client):
        """Test successful registration with all required fields."""
        payload = {
            "email": "ramesh@kirana.com",
            "name": "Ramesh",
            "surname": "Kumar",
            "shop_name": "Kumar General Store",
            "phone": "9876543211",
            "password": "strongPassword123",
        }
        res = client.post("/api/auth/signup", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "ramesh@kirana.com"
        assert data["user"]["name"] == "Ramesh"
        assert data["user"]["surname"] == "Kumar"
        assert data["user"]["shop_name"] == "Kumar General Store"
        assert data["user"]["phone"] == "9876543211"
        assert data["user"]["merchant_id"] is not None

    def test_signup_duplicate_email(self, client):
        """Test that duplicate email registration is rejected."""
        payload = {
            "email": "ramesh@kirana.com",
            "name": "Another",
            "surname": "Kumar",
            "shop_name": "Other Store",
            "phone": "9876543212",
            "password": "anotherPassword123",
        }
        res = client.post("/api/auth/signup", json=payload)
        assert res.status_code == 400
        data = res.json()
        assert data["error"]["code"] == "ERR_EMAIL_EXISTS"

    def test_signup_short_password(self, client):
        """Test that passwords shorter than 6 characters fail validation."""
        payload = {
            "email": "short@kirana.com",
            "name": "Short",
            "surname": "Pass",
            "shop_name": "Short Store",
            "phone": "9876543213",
            "password": "123",
        }
        res = client.post("/api/auth/signup", json=payload)
        assert res.status_code in (400, 422)

    def test_login_success(self, client):
        """Test login with valid email and password."""
        res = client.post(
            "/api/auth/login",
            json={"email": "ramesh@kirana.com", "password": "strongPassword123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["user"]["email"] == "ramesh@kirana.com"

    def test_login_wrong_password(self, client):
        """Test login fails with incorrect password."""
        res = client.post(
            "/api/auth/login",
            json={"email": "ramesh@kirana.com", "password": "wrongPassword"},
        )
        assert res.status_code == 401
        data = res.json()
        assert data["error"]["code"] == "ERR_INVALID_CREDENTIALS"

    def test_login_nonexistent_email(self, client):
        """Test login fails with nonexistent email."""
        res = client.post(
            "/api/auth/login",
            json={"email": "nobody@nowhere.com", "password": "somePassword"},
        )
        assert res.status_code == 401

    def test_auth_me_profile(self, client):
        """Test fetching the profile with Bearer token."""
        login_res = client.post(
            "/api/auth/login",
            json={"email": "ramesh@kirana.com", "password": "strongPassword123"},
        )
        token = login_res.json()["access_token"]

        # Without token -> 401
        unauth_res = client.get("/api/auth/me")
        assert unauth_res.status_code == 401

        # With token -> 200
        auth_res = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert auth_res.status_code == 200
        data = auth_res.json()
        assert data["email"] == "ramesh@kirana.com"
        assert data["shop_name"] == "Kumar General Store"

    def test_change_password_flow(self, client):
        """Test changing password and verifying new login works."""
        login_res = client.post(
            "/api/auth/login",
            json={"email": "ramesh@kirana.com", "password": "strongPassword123"},
        )
        token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 1. Attempt with incorrect current password
        bad_change = client.post(
            "/api/auth/change-password",
            json={"current_password": "incorrectOldPassword", "new_password": "newSecurePassword456"},
            headers=auth_headers,
        )
        assert bad_change.status_code == 400
        assert bad_change.json()["error"]["code"] == "ERR_INCORRECT_PASSWORD"

        # 2. Attempt with matching current password
        good_change = client.post(
            "/api/auth/change-password",
            json={"current_password": "strongPassword123", "new_password": "newSecurePassword456"},
            headers=auth_headers,
        )
        assert good_change.status_code == 200
        assert good_change.json()["success"] is True

        # 3. Old password should now fail
        old_login = client.post(
            "/api/auth/login",
            json={"email": "ramesh@kirana.com", "password": "strongPassword123"},
        )
        assert old_login.status_code == 401

        # 4. New password should succeed
        new_login = client.post(
            "/api/auth/login",
            json={"email": "ramesh@kirana.com", "password": "newSecurePassword456"},
        )
        assert new_login.status_code == 200

    def test_signup_long_password(self, client):
        """Test that passwords longer than 72 bytes do not crash bcrypt."""
        long_pass = "VeryLongPassword_That_Is_More_Than_72_Bytes_Long_And_Tests_Bcrypt_Safe_Truncation_1234567890"
        payload = {
            "email": "longpass@kirana.com",
            "name": "Long",
            "surname": "Pass",
            "shop_name": "Long Pass Store",
            "phone": "9876543219",
            "password": long_pass,
        }
        res = client.post("/api/auth/signup", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data

        # Login with the same long password
        login_res = client.post(
            "/api/auth/login",
            json={"email": "longpass@kirana.com", "password": long_pass},
        )
        assert login_res.status_code == 200

    def test_signup_invalid_email_format(self, client):
        """Test rejection of malformed email addresses."""
        payload = {
            "email": "invalid-email-address",
            "name": "Test",
            "surname": "User",
            "shop_name": "Test Store",
            "phone": "9876543220",
            "password": "validPassword123",
        }
        res = client.post("/api/auth/signup", json=payload)
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "ERR_INVALID_EMAIL"

    def test_signup_invalid_phone(self, client):
        """Test rejection of invalid/too-short phone number."""
        payload = {
            "email": "badphone@kirana.com",
            "name": "Test",
            "surname": "User",
            "shop_name": "Test Store",
            "phone": "123",
            "password": "validPassword123",
        }
        res = client.post("/api/auth/signup", json=payload)
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "ERR_INVALID_PHONE"

    def test_signup_empty_whitespace_fields(self, client):
        """Test rejection of whitespace-only names."""
        payload = {
            "email": "whitespace@kirana.com",
            "name": "   ",
            "surname": "User",
            "shop_name": "Test Store",
            "phone": "9876543221",
            "password": "validPassword123",
        }
        res = client.post("/api/auth/signup", json=payload)
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "ERR_INVALID_INPUT"

    def test_login_case_insensitive_email(self, client):
        """Test that logging in with uppercase or mixed-case email succeeds."""
        res = client.post(
            "/api/auth/login",
            json={"email": "RAMESH@KIRANA.COM", "password": "newSecurePassword456"},
        )
        assert res.status_code == 200

    def test_invalid_token_header(self, client):
        """Test that invalid or malformed tokens return 401."""
        res = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.malformed.token"},
        )
        assert res.status_code == 401



class TestDataIsolation:
    def test_strict_multi_tenant_isolation(self, client):
        """
        Verify that User A cannot see User B's transactions or dues.
        """
        # Register User A (Suresh Kirana)
        res_a = client.post(
            "/api/auth/signup",
            json={
                "email": "suresh@kirana.com",
                "name": "Suresh",
                "surname": "Patel",
                "shop_name": "Patel Provision",
                "phone": "9111111111",
                "password": "sureshPassword123",
            },
        )
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Register User B (Anita Stores)
        res_b = client.post(
            "/api/auth/signup",
            json={
                "email": "anita@kirana.com",
                "name": "Anita",
                "surname": "Sharma",
                "shop_name": "Anita Mart",
                "phone": "9222222222",
                "password": "anitaPassword123",
            },
        )
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A commits a transaction with udhar
        commit_payload_a = {
            "merchant_id": "ignored-will-be-overridden",
            "customer_name": "Customer Of Suresh",
            "customer_phone": "9998887771",
            "transaction_type": "SALE",
            "total_amount": "500.00",
            "cash_paid": "200.00",
            "upi_paid": "0.00",
            "credit_amount": "300.00",
            "raw_transcript": "Customer of suresh ne 500 ka samaan liya",
            "confidence_score": 0.95,
            "idempotency_hash": "hash-suresh-tx-001",
            "items": [{"item_name": "Atta", "quantity": "5kg", "unit_price": "500.00"}],
        }
        commit_res_a = client.post("/api/ledger/commit", json=commit_payload_a, headers=headers_a)
        assert commit_res_a.status_code == 200

        # Check User A ledger entries and summary
        entries_a = client.get("/api/ledger/entries", headers=headers_a).json()
        assert entries_a["total"] == 1
        assert entries_a["entries"][0]["customer_name"] == "Customer Of Suresh"

        summary_a = client.get("/api/ledger/summary", headers=headers_a).json()
        assert float(summary_a["total_credit_given"]) == 300.00
        assert float(summary_a["outstanding_udhaar"]) == 300.00

        # Check User B ledger entries and summary — MUST BE COMPLETELY EMPTY!
        entries_b = client.get("/api/ledger/entries", headers=headers_b).json()
        assert entries_b["total"] == 0
        assert len(entries_b["entries"]) == 0

        dues_b = client.get("/api/customers/dues", headers=headers_b).json()
        assert len(dues_b) == 0

        summary_b = client.get("/api/ledger/summary", headers=headers_b).json()
        assert float(summary_b["total_credit_given"]) == 0.00
        assert float(summary_b["outstanding_udhaar"]) == 0.00

        # Now User B commits their own transaction
        commit_payload_b = {
            "merchant_id": "ignored-will-be-overridden",
            "customer_name": "Customer Of Anita",
            "customer_phone": "9998887772",
            "transaction_type": "SALE",
            "total_amount": "1000.00",
            "cash_paid": "1000.00",
            "upi_paid": "0.00",
            "credit_amount": "0.00",
            "raw_transcript": "Customer of anita ne 1000 cash diya",
            "confidence_score": 0.99,
            "idempotency_hash": "hash-anita-tx-002",
            "items": [{"item_name": "Rice", "quantity": "10kg", "unit_price": "1000.00"}],
        }
        commit_res_b = client.post("/api/ledger/commit", json=commit_payload_b, headers=headers_b)
        assert commit_res_b.status_code == 200

        # Verify User A still only sees Suresh's transaction
        entries_a_again = client.get("/api/ledger/entries", headers=headers_a).json()
        assert entries_a_again["total"] == 1
        assert entries_a_again["entries"][0]["customer_name"] == "Customer Of Suresh"

        # Verify User B sees only Anita's transaction
        entries_b_again = client.get("/api/ledger/entries", headers=headers_b).json()
        assert entries_b_again["total"] == 1
        assert entries_b_again["entries"][0]["customer_name"] == "Customer Of Anita"


class TestPasswordReset:
    def test_forgot_password_success(self, client):
        """Test requesting password reset for registered user."""
        res = client.post("/api/auth/forgot-password", json={"email": "ramesh@kirana.com"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "ramesh@kirana.com" in data["message"]
        assert data["simulated_email"] is not None
        assert "code" in data["simulated_email"]
        assert len(data["simulated_email"]["code"]) == 6

    def test_forgot_password_nonexistent_email(self, client):
        """Test requesting password reset for unregistered email."""
        res = client.post("/api/auth/forgot-password", json={"email": "notfound@store.com"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "No account found" in data["message"]

    def test_reset_password_with_token(self, client):
        """Test resetting password using token link."""
        # Request reset
        req = client.post("/api/auth/forgot-password", json={"email": "ramesh@kirana.com"})
        sim_email = req.json()["simulated_email"]
        token = sim_email["token"]

        # Verify token is valid
        verify = client.get(f"/api/auth/verify-reset-token?token={token}")
        assert verify.status_code == 200
        assert verify.json()["valid"] is True

        # Reset password
        reset_res = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": "brandNewPassword789",
        })
        assert reset_res.status_code == 200
        assert reset_res.json()["success"] is True

        # Verify old password fails
        bad_login = client.post("/api/auth/login", json={
            "email": "ramesh@kirana.com",
            "password": "strongPassword123",
        })
        assert bad_login.status_code == 401

        # Verify new password succeeds
        good_login = client.post("/api/auth/login", json={
            "email": "ramesh@kirana.com",
            "password": "brandNewPassword789",
        })
        assert good_login.status_code == 200

        # Verify used token cannot be reused
        reuse_res = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": "anotherPassword999",
        })
        assert reuse_res.status_code == 400

    def test_reset_password_with_otp_code(self, client):
        """Test resetting password using 6-digit OTP code and email."""
        # Request reset
        req = client.post("/api/auth/forgot-password", json={"email": "ramesh@kirana.com"})
        sim_email = req.json()["simulated_email"]
        code = sim_email["code"]

        # Verify OTP code
        verify = client.get(f"/api/auth/verify-reset-token?code={code}&email=ramesh@kirana.com")
        assert verify.status_code == 200
        assert verify.json()["valid"] is True

        # Reset password
        reset_res = client.post("/api/auth/reset-password", json={
            "code": code,
            "email": "ramesh@kirana.com",
            "new_password": "passwordViaOtp123",
        })
        assert reset_res.status_code == 200

        # Login with newly reset password
        login = client.post("/api/auth/login", json={
            "email": "ramesh@kirana.com",
            "password": "passwordViaOtp123",
        })
        assert login.status_code == 200

    def test_reset_password_weak_password_rejected(self, client):
        """Test that passwords shorter than 6 chars are rejected during reset."""
        req = client.post("/api/auth/forgot-password", json={"email": "ramesh@kirana.com"})
        token = req.json()["simulated_email"]["token"]

        res = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": "123",
        })
        assert res.status_code in [400, 422]

    def test_latest_simulated_email_endpoint(self, client):
        """Test retrieving the latest simulated email for demo inspection."""
        client.post("/api/auth/forgot-password", json={"email": "ramesh@kirana.com"})
        res = client.get("/api/auth/latest-simulated-email?email=ramesh@kirana.com")
        assert res.status_code == 200
        data = res.json()
        assert data["recipient"] == "ramesh@kirana.com"
        assert len(data["code"]) == 6
        assert "html" in data
