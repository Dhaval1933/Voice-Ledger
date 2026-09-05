"""
Email notification service for Voice Ledger.

Handles:
- Branded, mobile-responsive HTML & plain-text password reset email generation
- Live SMTP dispatch if SMTP environment variables are configured
- In-memory simulated mailbox for zero-config hackathon demoing and judging
- Thread-safe buffer for instant retrieval by test suites and frontend preview modal
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import deque
import threading

from backend.config import get_settings

# Thread-safe in-memory ring buffer for simulated emails (keeps last 30 emails)
_MAILBOX_LOCK = threading.Lock()
_SIMULATED_MAILBOX: deque = deque(maxlen=30)


def generate_reset_email_html(
    name: str,
    email: str,
    reset_token: str,
    reset_code: str,
    reset_url: str,
    expires_in_minutes: int = 15,
) -> str:
    """Generate a responsive HTML email with Kirana Khata fintech branding."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your Password - Kirana Khata</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e6edf3;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0d1117; padding: 30px 15px;">
    <tr>
      <td align="center">
        <!-- Card Container -->
        <table role="presentation" width="100%" style="max-width: 560px; background: linear-gradient(180deg, #161b22 0%, #0d1117 100%); border: 1px solid #30363d; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
          <!-- Header Banner -->
          <tr>
            <td style="padding: 32px 32px 24px 32px; text-align: center; background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(16, 185, 129, 0.1) 100%); border-bottom: 1px solid #30363d;">
              <div style="display: inline-block; width: 52px; height: 52px; line-height: 52px; border-radius: 14px; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); font-size: 26px; box-shadow: 0 8px 16px rgba(99, 102, 241, 0.35);">
                🏪
              </div>
              <h1 style="margin: 14px 0 4px 0; font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">
                Kirana Khata
              </h1>
              <p style="margin: 0; font-size: 13px; color: #8b949e;">
                Voice-First AI Ledger & Smart Udhar Controller
              </p>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 32px;">
              <h2 style="margin: 0 0 14px 0; font-size: 18px; font-weight: 600; color: #ffffff;">
                Namaste {name} ji 🙏
              </h2>
              <p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.6; color: #c9d1d9;">
                We received a request to reset the password for your Kirana Khata merchant account (<strong>{email}</strong>). Use the 6-digit verification code below or click the direct button to set a new password.
              </p>

              <!-- 6-Digit Verification Code Box -->
              <div style="background-color: #090d13; border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0;">
                <p style="margin: 0 0 8px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; color: #8b949e; font-weight: 600;">
                  Your 6-Digit Password Reset Code
                </p>
                <div style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #58a6ff; font-family: 'Courier New', Courier, monospace; margin: 4px 0;">
                  {reset_code}
                </div>
                <p style="margin: 8px 0 0 0; font-size: 12px; color: #8b949e;">
                  Valid for <strong>{expires_in_minutes} minutes</strong>
                </p>
              </div>

              <!-- 1-Click CTA Button -->
              <div style="text-align: center; margin: 28px 0 20px 0;">
                <a href="{reset_url}" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #238636 0%, #2ea043 100%); color: #ffffff; text-decoration: none; font-size: 15px; font-weight: 600; padding: 14px 32px; border-radius: 10px; box-shadow: 0 6px 16px rgba(46, 160, 67, 0.35);">
                  Reset Password Directly →
                </a>
              </div>

              <p style="margin: 20px 0 0 0; font-size: 12px; color: #8b949e; line-height: 1.5; text-align: center;">
                If the button doesn't work, copy and paste this link in your browser:<br>
                <a href="{reset_url}" style="color: #58a6ff; word-break: break-all; font-size: 11px;">{reset_url}</a>
              </p>

              <hr style="border: none; border-top: 1px solid #21262d; margin: 28px 0 20px 0;">

              <!-- Security Notice -->
              <p style="margin: 0; font-size: 12px; line-height: 1.6; color: #8b949e;">
                🛡️ <strong>Security Tip:</strong> If you did not request this password reset, you can safely ignore this email. Your account password remains unchanged.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #090d13; border-top: 1px solid #21262d; text-align: center;">
              <p style="margin: 0; font-size: 11px; color: #484f58;">
                Built with ❤️ for Indian Retail Kirana Stores • Powered by Razorpay Payment Rails
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def generate_reset_email_text(
    name: str,
    email: str,
    reset_code: str,
    reset_url: str,
    expires_in_minutes: int = 15,
) -> str:
    """Generate plain-text email fallback."""
    return (
        f"Namaste {name} ji,\n\n"
        f"We received a request to reset your password for Kirana Khata ({email}).\n\n"
        f"Your 6-digit reset code is: {reset_code}\n\n"
        f"Or reset directly via this link:\n{reset_url}\n\n"
        f"This code will expire in {expires_in_minutes} minutes.\n\n"
        f"If you did not make this request, please ignore this email.\n\n"
        f"---\n"
        f"Kirana Khata - Voice-First AI Ledger"
    )


def send_password_reset_email(
    user_email: str,
    user_name: str,
    reset_token: str,
    reset_code: str,
    expires_in_minutes: int = 15,
) -> Dict[str, Any]:
    """
    Send a password reset email to the user.
    
    If SMTP credentials are configured in Settings, dispatches live email.
    Otherwise, captures in simulated mailbox for instant testing & hackathon demos.
    """
    settings = get_settings()
    subject = f"🔒 {reset_code} is your Kirana Khata password reset code"
    frontend_origin = settings.FRONTEND_ORIGIN.rstrip("/")
    reset_url = f"{frontend_origin}/?reset_token={reset_token}&email={user_email}"

    html_content = generate_reset_email_html(
        name=user_name,
        email=user_email,
        reset_token=reset_token,
        reset_code=reset_code,
        reset_url=reset_url,
        expires_in_minutes=expires_in_minutes,
    )
    text_content = generate_reset_email_text(
        name=user_name,
        email=user_email,
        reset_code=reset_code,
        reset_url=reset_url,
        expires_in_minutes=expires_in_minutes,
    )

    now = datetime.now(timezone.utc)
    email_record = {
        "recipient": user_email,
        "name": user_name,
        "subject": subject,
        "code": reset_code,
        "token": reset_token,
        "reset_url": reset_url,
        "expires_in_minutes": expires_in_minutes,
        "html": html_content,
        "text": text_content,
        "sent_at": now.isoformat(),
        "dispatched_via": "simulated",
    }

    # If live SMTP host is specified in environment, dispatch live email
    if settings.SMTP_HOST:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.EMAILS_FROM
            msg["To"] = user_email

            part1 = MIMEText(text_content, "plain")
            part2 = MIMEText(html_content, "html")
            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAILS_FROM, [user_email], msg.as_string())

            email_record["dispatched_via"] = "smtp"
        except Exception as e:
            # Fallback to simulated delivery gracefully if SMTP server fails
            email_record["smtp_error"] = str(e)
            email_record["dispatched_via"] = "simulated (smtp failed)"

    # Store in thread-safe ring buffer for frontend preview and tests
    with _MAILBOX_LOCK:
        _SIMULATED_MAILBOX.append(email_record)

    return email_record


def get_latest_simulated_email(email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve the most recent simulated email (optionally for a specific recipient)."""
    with _MAILBOX_LOCK:
        if not _SIMULATED_MAILBOX:
            return None
        if not email:
            return _SIMULATED_MAILBOX[-1]

        email_clean = email.strip().lower()
        for item in reversed(_SIMULATED_MAILBOX):
            if item.get("recipient", "").lower() == email_clean:
                return item
        return None


def get_all_simulated_emails() -> List[Dict[str, Any]]:
    """Retrieve all simulated emails in memory."""
    with _MAILBOX_LOCK:
        return list(_SIMULATED_MAILBOX)


def clear_simulated_mailbox() -> None:
    """Clear in-memory simulated mailbox (useful for testing)."""
    with _MAILBOX_LOCK:
        _SIMULATED_MAILBOX.clear()
