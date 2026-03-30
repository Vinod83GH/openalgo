import os
import threading

from cachetools import TTLCache
from sqlalchemy import Boolean, Column, Integer, Numeric, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

from utils.logging import get_logger

logger = get_logger(__name__)

# TTLCache keyed by f"kill_switch:{broker_name}", TTL = 60 seconds
_kill_switch_cache = TTLCache(maxsize=128, ttl=60)
_cache_lock = threading.Lock()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL, poolclass=NullPool, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL, pool_size=50, max_overflow=100, pool_timeout=10)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()


class KillSwitchConfig(Base):
    __tablename__ = "kill_switch_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    broker_name = Column(String(64), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=False)
    profit_threshold = Column(Numeric(18, 4), nullable=False, default=0)
    loss_threshold = Column(Numeric(18, 4), nullable=False, default=0)
    kill_switch_status = Column(String(16), nullable=False, default="DEACTIVATED")
    # Cached P&L updated by PnL monitor — avoids live broker calls on status fetch
    current_pnl = Column(Numeric(18, 2), nullable=False, default=0)


def init_db():
    """Create the kill_switch_config table if it does not exist."""
    from database.db_init_helper import init_db_with_logging
    init_db_with_logging(Base, engine, "Kill Switch DB", logger)


def _cache_key(broker_name: str) -> str:
    return f"kill_switch:{broker_name}"


def invalidate_kill_switch_cache(broker_name: str) -> None:
    key = _cache_key(broker_name)
    with _cache_lock:
        if key in _kill_switch_cache:
            del _kill_switch_cache[key]


def get_kill_switch_config(broker_name: str) -> KillSwitchConfig:
    """Return the KillSwitchConfig for broker_name, creating a default record if none exists."""
    key = _cache_key(broker_name)

    with _cache_lock:
        if key in _kill_switch_cache:
            return _kill_switch_cache[key]

    config = KillSwitchConfig.query.filter_by(broker_name=broker_name).first()
    if config is None:
        config = KillSwitchConfig(
            broker_name=broker_name,
            enabled=False,
            profit_threshold=0,
            loss_threshold=0,
            kill_switch_status="DEACTIVATED",
            current_pnl=0,
        )
        try:
            db_session.add(config)
            db_session.commit()
        except Exception as e:
            db_session.rollback()
            logger.debug(f"Kill Switch DB: Default config may already exist (race condition): {e}")
            config = KillSwitchConfig.query.filter_by(broker_name=broker_name).first()

    with _cache_lock:
        _kill_switch_cache[key] = config

    return config


def upsert_kill_switch_config(broker_name: str, **fields) -> KillSwitchConfig:
    """Update or insert kill switch config fields for broker_name."""
    config = KillSwitchConfig.query.filter_by(broker_name=broker_name).first()
    if config is None:
        config = KillSwitchConfig(broker_name=broker_name)
        db_session.add(config)

    for field, value in fields.items():
        if hasattr(config, field):
            setattr(config, field, value)

    db_session.commit()
    invalidate_kill_switch_cache(broker_name)
    return config


def update_kill_switch_status_cache(broker_name: str, status: str) -> None:
    """Update the kill_switch_status column and invalidate the TTLCache entry."""
    config = KillSwitchConfig.query.filter_by(broker_name=broker_name).first()
    if config is None:
        config = KillSwitchConfig(
            broker_name=broker_name,
            enabled=False,
            profit_threshold=0,
            loss_threshold=0,
            kill_switch_status=status,
            current_pnl=0,
        )
        db_session.add(config)
    else:
        config.kill_switch_status = status

    db_session.commit()
    invalidate_kill_switch_cache(broker_name)


def update_kill_switch_pnl(broker_name: str, pnl: float) -> None:
    """Update the cached current_pnl value for a broker (called by PnL monitor)."""
    config = KillSwitchConfig.query.filter_by(broker_name=broker_name).first()
    if config is not None:
        config.current_pnl = round(pnl, 2)
        db_session.commit()
        invalidate_kill_switch_cache(broker_name)


def is_kill_switch_active(broker_name: str) -> bool:
    """Return True when the cached kill_switch_status is 'ACTIVATED'."""
    key = _cache_key(broker_name)

    with _cache_lock:
        if key in _kill_switch_cache:
            cached = _kill_switch_cache[key]
            return cached.kill_switch_status == "ACTIVATED"

    config = get_kill_switch_config(broker_name)
    return config.kill_switch_status == "ACTIVATED"
