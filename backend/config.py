"""
Application configuration via environment variables.
Uses Pydantic BaseSettings for validated, typed config with .env file support.
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # Database
    DATABASE_URL: str = "sqlite:///./ledger.db"

    # AI Provider Selection: "mock", "openai", "groq"
    ASR_PROVIDER: str = "mock"
    LLM_PROVIDER: str = "mock"

    # API Keys (only needed when provider != "mock")
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    # Merchant UPI VPA for demo
    MERCHANT_VPA: str = "demo@upi"
    MERCHANT_NAME: str = "Demo Kirana Store"

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Audio upload limits
    MAX_AUDIO_SIZE_MB: int = 10

    # Demo merchant ID (fixed UUID for single-merchant demo)
    DEMO_MERCHANT_ID: str = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    # JWT Authentication
    JWT_SECRET_KEY: str = "voice-ledger-secret-jwt-key-sharma-kirana-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    PASSWORD_RESET_EXPIRE_MINUTES: int = 15  # 15 minutes

    # Razorpay Payment Rails & Webhooks
    RAZORPAY_KEY_ID: str = "rzp_test_kirana_demo"
    RAZORPAY_KEY_SECRET: str = "rzp_secret_kirana_demo"
    RAZORPAY_WEBHOOK_SECRET: str = "whsec_kirana_buildathon_demo"

    # Email / SMTP Configuration
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM: str = "support@kirana-khata.in"
    SMTP_USE_TLS: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
