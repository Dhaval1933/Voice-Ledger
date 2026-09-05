"""
Recovery service for UPI deep link generation and WhatsApp reminder dispatch.

Generates:
- UPI deep links per NPCI specification
- WhatsApp click-to-chat URLs with polite Hinglish reminders

This is a MOCK WhatsApp integration — it generates valid URLs but
does not actually send messages via the WhatsApp Business API.
"""

from decimal import Decimal
from urllib.parse import quote, quote_plus
from typing import Optional


def generate_upi_deep_link(
    merchant_vpa: str,
    merchant_name: str,
    amount: Decimal,
    transaction_reference: str,
) -> str:
    """
    Generate a UPI deep link following the NPCI specification.

    Format: upi://pay?pa={vpa}&pn={name}&am={amount}&cu=INR&tn={ref}

    All values are URL-encoded for safety.
    """
    params = {
        "pa": merchant_vpa,
        "pn": merchant_name,
        "am": str(amount.quantize(Decimal("0.01"))),
        "cu": "INR",
        "tn": transaction_reference,
    }

    query_string = "&".join(
        f"{key}={quote(str(value), safe='')}"
        for key, value in params.items()
    )

    return f"upi://pay?{query_string}"


def generate_whatsapp_reminder(
    customer_name: str,
    customer_phone: Optional[str],
    amount: Decimal,
    upi_link: str,
    merchant_name: str = "Dukan",
) -> dict:
    """
    Generate a WhatsApp click-to-chat URL with a polite Hinglish reminder.

    Returns:
        {
            "whatsapp_url": "https://wa.me/...",
            "message": "...",
            "phone_used": "..."
        }

    NOTE: This is a MOCK — it generates valid URLs but does NOT
    actually send messages via WhatsApp Business API.
    """
    # Format amount with Indian comma notation
    formatted_amount = format_indian_currency(amount)

    message = (
        f"🙏 Namaste {customer_name},\n\n"
        f"Aapka {formatted_amount} ka pending Udhar hai "
        f"{merchant_name} mein.\n\n"
        f"Aap yahan se UPI payment kar sakte hain:\n"
        f"{upi_link}\n\n"
        f"Dhanyavaad! 🙏"
    )

    # Clean phone number — remove spaces, dashes, ensure country code
    phone = clean_phone_for_whatsapp(customer_phone)

    whatsapp_url = f"https://wa.me/{phone}?text={quote_plus(message)}"

    return {
        "whatsapp_url": whatsapp_url,
        "message": message,
        "phone_used": phone,
    }


def clean_phone_for_whatsapp(phone: Optional[str]) -> str:
    """Clean and format phone number for WhatsApp API.

    Ensures number starts with country code (defaults to India +91).
    """
    if not phone:
        return "919876543210"  # Demo fallback number

    # Remove all non-digit characters except leading +
    import re
    cleaned = re.sub(r"[^\d+]", "", phone)

    # Remove leading +
    cleaned = cleaned.lstrip("+")

    # Add India country code if not present
    # A valid Indian international number is 12+ digits starting with "91"
    # A 10-digit number starting with "91" is a local number, not country-coded
    if len(cleaned) == 10:
        cleaned = "91" + cleaned
    elif not cleaned.startswith("91") and len(cleaned) > 10:
        cleaned = "91" + cleaned

    return cleaned


def format_indian_currency(amount: Decimal) -> str:
    """Format a Decimal amount in Indian currency notation.

    Examples:
        1234.00 → ₹1,234
        123456.00 → ₹1,23,456
        1234567.00 → ₹12,34,567
    """
    amount_str = str(int(amount))
    if len(amount_str) <= 3:
        return f"₹{amount_str}"

    # Indian notation: last 3 digits, then groups of 2
    last_three = amount_str[-3:]
    remaining = amount_str[:-3]

    # Add commas every 2 digits in the remaining part
    groups = []
    while remaining:
        groups.append(remaining[-2:])
        remaining = remaining[:-2]

    groups.reverse()
    formatted = ",".join(groups) + "," + last_three

    return f"₹{formatted}"
