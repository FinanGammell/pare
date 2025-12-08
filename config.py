"""
Application configuration for Pare.

This file handles all configuration settings for the Flask app, including:
- Database connection settings
- OAuth credentials (Google Client ID/Secret)
- Session cookie settings
- Environment detection (development vs production)
"""
from __future__ import annotations

import os
import secrets
import warnings
from pathlib import Path

# Get the base directory of the project (where this file is located)
BASE_DIR = Path(__file__).resolve().parent
# SQLite database file path
DB_PATH = BASE_DIR / "pare.sqlite3"


def in_railway() -> bool:
    """
    Check if running on Railway platform.
    
    Railway sets RAILWAY_PUBLIC_DOMAIN when the app is deployed there.
    We use this to detect if we're in production.
    """
    return bool(os.getenv("RAILWAY_PUBLIC_DOMAIN"))


def is_production() -> bool:
    """
    Check if running in production environment.
    
    Production means either:
    - Running on Railway (has RAILWAY_PUBLIC_DOMAIN)
    - FLASK_ENV is explicitly set to "production"
    """
    return in_railway() or os.getenv("FLASK_ENV") == "production"


def _get_secret_key() -> str:
    """
    Get SECRET_KEY from environment, with production validation.
    
    The secret key is used to encrypt session cookies. Without it, OAuth won't work
    because we can't securely store the OAuth state in the session.
    
    In production, this MUST be set. In development, we can auto-generate one.
    """
    key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
    
    if not key:
        # No key set
        if is_production():
            # Production requires a real key - fail fast
            raise RuntimeError(
                "FLASK_SECRET_KEY missing — OAuth cannot maintain state. "
                "Set this in Railway → Service → Variables."
            )
        # Development: auto-generate a temporary key
        # This is fine for local testing, but sessions won't persist across restarts
        key = secrets.token_urlsafe(32)
        warnings.warn(
            f"FLASK_SECRET_KEY not set. Using auto-generated dev key: {key[:8]}... "
            "Set FLASK_SECRET_KEY in .env for consistent sessions.",
            UserWarning,
        )
    elif key == "dev-secret-key":
        # Using the default dev key
        if is_production():
            # Never use the dev key in production - it's not secure
            raise RuntimeError(
                "FLASK_SECRET_KEY cannot be 'dev-secret-key' in production. "
                "Set a secure random key in Railway → Service → Variables."
            )
        warnings.warn(
            "FLASK_SECRET_KEY is set to default 'dev-secret-key'. "
            "Use a secure random key for production.",
            UserWarning,
        )
    
    return key


def _get_google_redirect_uri() -> str:
    """
    Get GOOGLE_REDIRECT_URI from env or construct from Railway domain.
    
    The redirect URI is where Google sends users after they log in.
    It must match exactly what's configured in Google Cloud Console.
    
    Priority:
    1. GOOGLE_REDIRECT_URI environment variable (if set)
    2. Construct from Railway domain (if on Railway)
    3. Development fallback (localhost:5001)
    """
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    
    if redirect_uri:
        return redirect_uri
    
    # Construct from Railway domain if available
    # Railway gives us a public domain, so we can build the redirect URI automatically
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        return f"https://{railway_domain}/oauth2callback"
    
    # Development fallback
    # In development, the backend runs on localhost:5001
    return "http://localhost:5001/oauth2callback"


def _require_env_var(name: str, value: str | None, production_only: bool = False) -> str:
    """Require an environment variable, raising RuntimeError if missing in production."""
    if not value:
        if is_production() or not production_only:
            raise RuntimeError(
                f"{name} missing. Set this in Railway → Service → Variables "
                f"or in your .env file for local development."
            )
        warnings.warn(f"{name} not set. Some features may not work.", UserWarning)
    return value or ""


class BaseConfig:
    """
    Base configuration shared across environments.
    
    This class contains all the configuration settings that apply to all environments
    (development, production, testing). Environment-specific configs inherit from this.
    """

    # Database connection string
    # In production, Railway might provide DATABASE_URL (PostgreSQL)
    # In development, we use SQLite (a local file database)
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Disable Flask-SQLAlchemy event tracking (not needed)

    # Session cookie configuration for production OAuth stability
    # These settings control how Flask stores session data in browser cookies
    
    # Secure=True means cookies only sent over HTTPS (required in production)
    # SameSite=None is REQUIRED for OAuth cross-site redirects (Google → our callback)
    # When Google redirects to our callback, it's a cross-site request, so we need SameSite=None
    # Secure=True is required when SameSite=None (enforced by browsers)
    SESSION_COOKIE_SECURE = is_production()  # Only use HTTPS cookies in production
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript from accessing cookies (security)
    SESSION_COOKIE_SAMESITE = "None" if is_production() else "Lax"  # Allow cross-site in production
    SESSION_COOKIE_DOMAIN = None  # Don't restrict cookie to a specific domain

    # OAuth scopes - what permissions we're asking Google for
    GOOGLE_SCOPES = [
        "openid",  # Basic user identity
        "https://www.googleapis.com/auth/userinfo.email",  # User's email address
        "https://www.googleapis.com/auth/userinfo.profile",  # User's name
        "https://www.googleapis.com/auth/gmail.readonly",  # Read Gmail (but not send/delete)
    ]

    # Secret key for encrypting session cookies
    SECRET_KEY = _get_secret_key()

    # Google OAuth credentials - get these from Google Cloud Console
    GOOGLE_CLIENT_ID = _require_env_var("GOOGLE_CLIENT_ID", os.getenv("GOOGLE_CLIENT_ID"))
    GOOGLE_CLIENT_SECRET = _require_env_var(
        "GOOGLE_CLIENT_SECRET", os.getenv("GOOGLE_CLIENT_SECRET")
    )
    # Where Google redirects users after login
    GOOGLE_REDIRECT_URI = _get_google_redirect_uri()

    # OpenAI API key for email classification
    # Only required in production (can be missing in development for testing)
    OPENAI_API_KEY = _require_env_var(
        "OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"), production_only=True
    )

    # Railway public domain (if deployed on Railway)
    RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")


def _get_secret_key_prod() -> str:
    """Require SECRET_KEY in production."""
    key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
    if not key or key == "dev-secret-key":
        raise RuntimeError(
            "FLASK_SECRET_KEY missing or invalid in production. "
            "Set a secure random key in Railway → Service → Variables."
        )
    return key


def _get_google_redirect_uri_prod() -> str:
    """Require GOOGLE_REDIRECT_URI in production."""
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    
    if redirect_uri:
        return redirect_uri
    
    if railway_domain:
        return f"https://{railway_domain}/oauth2callback"
    
    raise RuntimeError(
        "GOOGLE_REDIRECT_URI missing. Set GOOGLE_REDIRECT_URI or RAILWAY_PUBLIC_DOMAIN "
        "in Railway → Service → Variables."
    )


class ProductionConfig(BaseConfig):
    """Production configuration — requires all OAuth variables and secret keys."""

    SECRET_KEY = _get_secret_key_prod()
    GOOGLE_REDIRECT_URI = _get_google_redirect_uri_prod()


class DevelopmentConfig(BaseConfig):
    """Development configuration — allows localhost defaults and dev keys."""

    # Inherits BaseConfig which already handles dev fallbacks


class TestConfig(BaseConfig):
    """Configuration overrides used for tests."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key"
    GOOGLE_CLIENT_ID = "test-client-id"
    GOOGLE_CLIENT_SECRET = "test-client-secret"
    GOOGLE_REDIRECT_URI = "http://localhost:5001/oauth2callback"
    OPENAI_API_KEY = "test-openai-key"


# Default to BaseConfig which auto-detects environment
Config = BaseConfig
