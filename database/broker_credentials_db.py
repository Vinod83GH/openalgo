# database/broker_credentials_db.py

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import func

from utils.logging import get_logger

logger = get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Follow the same engine pattern as kill_switch_db.py
if DATABASE_URL and "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL, poolclass=NullPool, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL, pool_size=50, max_overflow=100, pool_timeout=10)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()


# --- Fernet encryption setup (same key derivation as auth_db.py) ---

def _get_encryption_key():
    """Generate a Fernet key from APP_KEY / API_KEY_PEPPER env variable.

    Uses the same PBKDF2 derivation as database/auth_db.py so that the
    encryption is consistent across the application.
    """
    pepper = os.getenv("API_KEY_PEPPER", "")
    if not pepper:
        raise RuntimeError(
            "CRITICAL: API_KEY_PEPPER environment variable is not set. "
            "Cannot encrypt broker credentials."
        )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"openalgo_static_salt",
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(pepper.encode()))
    return Fernet(key)


_fernet = _get_encryption_key()


def encrypt_secret(value: str) -> str:
    """Encrypt a plaintext secret using Fernet.

    Args:
        value: The plaintext string to encrypt.

    Returns:
        The encrypted string (base64-encoded ciphertext).
    """
    if not value:
        return ""
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(encrypted_value: str) -> str:
    """Decrypt a Fernet-encrypted secret back to plaintext.

    Args:
        encrypted_value: The encrypted string to decrypt.

    Returns:
        The decrypted plaintext string, or None on failure.
    """
    if not encrypted_value:
        return ""
    try:
        return _fernet.decrypt(encrypted_value.encode()).decode()
    except Exception as e:
        logger.exception(f"Error decrypting broker secret: {e}")
        return None


# --- SQLAlchemy Model ---

class BrokerCredential(Base):
    __tablename__ = "broker_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False)
    broker_name = Column(String(50), nullable=False)
    api_key = Column(Text, nullable=True)
    api_secret_encrypted = Column(Text, nullable=True)
    client_id = Column(String(255), nullable=True)
    redirect_url = Column(Text, nullable=True)
    additional_config = Column(Text, nullable=True)  # JSON text for broker-specific extras
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("username", "broker_name", name="uq_user_broker"),
        Index("idx_broker_cred_username", "username"),
    )


# --- Database initialization ---

def init_db():
    """Create the broker_credentials table if it does not exist."""
    from database.db_init_helper import init_db_with_logging

    init_db_with_logging(Base, engine, "Broker Credentials DB", logger)


# --- CRUD Helpers ---


def mask_secret(value, show_chars=4):
    """Return a masked version of a secret string for safe display.

    Shows the first `show_chars` characters and replaces the rest with asterisks.

    Args:
        value: The secret string to mask.
        show_chars: Number of leading characters to keep visible (default 4).

    Returns:
        Masked string, or empty string if value is None/empty.
    """
    if not value:
        return ""
    if len(value) <= show_chars:
        return value
    return value[:show_chars] + "*" * (len(value) - show_chars)


def save_credentials(username, broker_name, api_key, api_secret, client_id, redirect_url, additional_config=None):
    """Upsert broker credentials for a user.

    If a record already exists for (username, broker_name), update it;
    otherwise insert a new record. The api_secret is encrypted before storage.

    Args:
        username: The app username.
        broker_name: The broker identifier (e.g. "dhan", "angel").
        api_key: The broker API key (stored plaintext).
        api_secret: The broker API secret (encrypted before storage).
        client_id: The broker client ID (stored plaintext).
        redirect_url: The OAuth redirect URL (stored plaintext).
        additional_config: Optional JSON string for broker-specific extras.

    Returns:
        True on success, False on failure.
    """
    try:
        existing = db_session.query(BrokerCredential).filter_by(
            username=username, broker_name=broker_name
        ).first()

        encrypted_secret = encrypt_secret(api_secret) if api_secret else ""

        if existing:
            existing.api_key = api_key
            existing.api_secret_encrypted = encrypted_secret
            existing.client_id = client_id
            existing.redirect_url = redirect_url
            existing.additional_config = additional_config
        else:
            new_cred = BrokerCredential(
                username=username,
                broker_name=broker_name,
                api_key=api_key,
                api_secret_encrypted=encrypted_secret,
                client_id=client_id,
                redirect_url=redirect_url,
                additional_config=additional_config,
            )
            db_session.add(new_cred)

        db_session.commit()
        return True
    except Exception as e:
        logger.exception(f"Error saving broker credentials for {username}/{broker_name}: {e}")
        db_session.rollback()
        return False


def get_credentials(username, broker_name):
    """Retrieve decrypted broker credentials for a user and broker.

    Args:
        username: The app username.
        broker_name: The broker identifier.

    Returns:
        Dict with api_key, api_secret (decrypted), client_id, redirect_url,
        additional_config, broker_name — or None if not found.
    """
    try:
        cred = db_session.query(BrokerCredential).filter_by(
            username=username, broker_name=broker_name
        ).first()

        if not cred:
            return None

        return {
            "broker_name": cred.broker_name,
            "api_key": cred.api_key,
            "api_secret": decrypt_secret(cred.api_secret_encrypted),
            "client_id": cred.client_id,
            "redirect_url": cred.redirect_url,
            "additional_config": cred.additional_config,
        }
    except Exception as e:
        logger.exception(f"Error retrieving broker credentials for {username}/{broker_name}: {e}")
        return None


def get_all_credentials(username):
    """Retrieve all broker credentials for a user with secrets masked.

    Args:
        username: The app username.

    Returns:
        List of dicts, each with api_key, api_secret (masked), client_id,
        redirect_url, additional_config, broker_name.
    """
    try:
        creds = db_session.query(BrokerCredential).filter_by(username=username).all()

        result = []
        for cred in creds:
            result.append({
                "broker_name": cred.broker_name,
                "api_key": cred.api_key,
                "api_secret": mask_secret(decrypt_secret(cred.api_secret_encrypted)),
                "client_id": cred.client_id,
                "redirect_url": cred.redirect_url,
                "additional_config": cred.additional_config,
            })
        return result
    except Exception as e:
        logger.exception(f"Error retrieving all broker credentials for {username}: {e}")
        return []


def delete_credentials(username, broker_name):
    """Delete stored broker credentials for a user and broker.

    Args:
        username: The app username.
        broker_name: The broker identifier.

    Returns:
        True if credentials were found and deleted, False otherwise.
    """
    try:
        cred = db_session.query(BrokerCredential).filter_by(
            username=username, broker_name=broker_name
        ).first()

        if not cred:
            return False

        db_session.delete(cred)
        db_session.commit()
        return True
    except Exception as e:
        logger.exception(f"Error deleting broker credentials for {username}/{broker_name}: {e}")
        db_session.rollback()
        return False
