# database/tv_strategy_db.py

import os
import threading

from cachetools import TTLCache
from sqlalchemy import Boolean, Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

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

# Valid enum values
VALID_EXCHANGES = {"NFO", "BFO", "MCX", "CDS"}
VALID_PRODUCTS = {"MIS", "NRML"}
VALID_STRIKE_SELECTIONS = [
    "ITM5", "ITM4", "ITM3", "ITM2", "ITM1",
    "ATM",
    "OTM1", "OTM2", "OTM3", "OTM4", "OTM5",
]
ALL_WEEKDAYS = "Mon,Tue,Wed,Thu,Fri"

# TTLCache keyed by strategy name, TTL = 60 seconds
_strategy_cache = TTLCache(maxsize=128, ttl=60)
_cache_lock = threading.Lock()


class TvStrategy(Base):
    __tablename__ = "tv_strategy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    active_days = Column(String(50), nullable=False, default=ALL_WEEKDAYS)
    lot_size = Column(Integer, nullable=False, default=1)
    strike_selection = Column(String(10), nullable=False, default="ITM2")
    enabled = Column(Boolean, nullable=False, default=True)
    product = Column(String(10), nullable=False, default="MIS")
    exchange = Column(String(10), nullable=False, default="NFO")


def init_db():
    """Create the tv_strategy table if it does not exist."""
    from database.db_init_helper import init_db_with_logging

    init_db_with_logging(Base, engine, "TV Strategy DB", logger)


def invalidate_strategy_cache(name: str) -> None:
    """Remove the entry for a strategy name from the TTLCache."""
    with _cache_lock:
        if name in _strategy_cache:
            del _strategy_cache[name]


def get_strategy_by_name(name: str):
    """Look up a strategy by name (cached 60s).

    Returns the TvStrategy record or None if not found.
    """
    with _cache_lock:
        if name in _strategy_cache:
            return _strategy_cache[name]

    # Cache miss — query DB
    strategy = TvStrategy.query.filter_by(name=name).first()
    if strategy:
        with _cache_lock:
            _strategy_cache[name] = strategy
    return strategy


def get_all_strategies():
    """Return all TvStrategy records ordered by name."""
    return TvStrategy.query.order_by(TvStrategy.name).all()


def create_strategy(name: str, **fields):
    """Create a new TvStrategy. Raises ValueError on validation failures."""
    _validate_fields(fields)
    strategy = TvStrategy(name=name, **fields)
    try:
        db_session.add(strategy)
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise e
    return strategy


def update_strategy(strategy, **fields):
    """Update an existing TvStrategy. Raises ValueError on validation failures."""
    _validate_fields(fields)
    try:
        for key, value in fields.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise e
    invalidate_strategy_cache(strategy.name)
    return strategy


def delete_strategy(strategy) -> None:
    """Delete a TvStrategy record."""
    name = strategy.name
    try:
        db_session.delete(strategy)
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise e
    invalidate_strategy_cache(name)


def _validate_fields(fields: dict) -> None:
    """Validate field values. Raises ValueError with descriptive message."""
    if "lot_size" in fields and fields["lot_size"] < 1:
        raise ValueError("lot_size must be at least 1")
    if "exchange" in fields and fields["exchange"] not in VALID_EXCHANGES:
        raise ValueError(f"exchange must be one of: {', '.join(sorted(VALID_EXCHANGES))}")
    if "product" in fields and fields["product"] not in VALID_PRODUCTS:
        raise ValueError(f"product must be one of: {', '.join(sorted(VALID_PRODUCTS))}")
    if "strike_selection" in fields and fields["strike_selection"] not in VALID_STRIKE_SELECTIONS:
        raise ValueError(f"strike_selection must be one of: {', '.join(VALID_STRIKE_SELECTIONS)}")
