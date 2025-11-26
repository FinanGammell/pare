"""Application configuration for Pare."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "pare.sqlite3"


class Config:
    """Base configuration shared across environments."""

    # Use FLASK_SECRET_KEY for Railway compatibility, fallback to SECRET_KEY
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY", "dev-secret-key")
    if not SECRET_KEY or SECRET_KEY == "dev-secret-key":
        import warnings
        warnings.warn(
            "SECRET_KEY not set or using dev default. Set FLASK_SECRET_KEY or SECRET_KEY env var for production.",
            UserWarning,
        )
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    # GOOGLE_REDIRECT_URI will be constructed dynamically using url_for in google_auth.py
    # This fallback is only used if url_for fails
    GOOGLE_REDIRECT_URI = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "",  # Empty default - will be set dynamically
    )
    GOOGLE_SCOPES = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "openid",
    ]

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # Railway-specific: Get public domain if available
    RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")


class TestConfig(Config):
    """Configuration overrides used for tests."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
