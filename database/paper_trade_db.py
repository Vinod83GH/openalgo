# database/paper_trade_db.py

import os
from datetime import date

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    func,
)
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


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    trade_date = Column(Date, nullable=True)
    strategy_name = Column(String(128), nullable=False)
    direction = Column(String(16), nullable=True)
    entry_time = Column(DateTime(timezone=True), nullable=True)
    entry_spot_price = Column(Numeric(18, 4), nullable=True)
    entry_option_symbol = Column(String(64), nullable=True)
    entry_option_price = Column(Numeric(18, 4), nullable=True)
    entry_quantity = Column(Integer, nullable=True)
    entry_action = Column(String(8), nullable=True)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    exit_spot_price = Column(Numeric(18, 4), nullable=True)
    exit_option_price = Column(Numeric(18, 4), nullable=True)
    exit_reason = Column(String(32), nullable=True)
    pnl = Column(Numeric(18, 4), nullable=True)
    custom_metadata = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_paper_trades_date", "trade_date"),
        Index("idx_paper_trades_strategy", "strategy_name"),
        Index("idx_paper_trades_date_strategy", "trade_date", "strategy_name"),
    )


def init_db():
    """Create the paper_trades table if it does not exist."""
    from database.db_init_helper import init_db_with_logging

    init_db_with_logging(Base, engine, "Paper Trade DB", logger)


def create_trade(**fields) -> PaperTrade:
    """Insert a new trade record with the provided fields.

    Args:
        **fields: Column values for the new PaperTrade record.
                  `strategy_name` is required.

    Returns:
        The newly created PaperTrade instance.
    """
    trade = PaperTrade(**fields)
    db_session.add(trade)
    db_session.commit()
    return trade


def get_trade(trade_id: int) -> PaperTrade | None:
    """Fetch a single trade by ID.

    Returns:
        The PaperTrade instance, or None if not found.
    """
    return PaperTrade.query.filter_by(id=trade_id).first()


def update_trade(trade_id: int, **fields) -> PaperTrade | None:
    """Update specified fields on an existing trade.

    Args:
        trade_id: The ID of the trade to update.
        **fields: Column values to update.

    Returns:
        The updated PaperTrade instance, or None if not found.
    """
    trade = PaperTrade.query.filter_by(id=trade_id).first()
    if trade is None:
        return None

    for field, value in fields.items():
        if hasattr(trade, field):
            setattr(trade, field, value)

    db_session.commit()
    return trade


def query_trades(
    start_date=None, end_date=None, strategy_name=None
) -> list[PaperTrade]:
    """Filter trades by date range and/or strategy.

    When no filters are provided, defaults to the current date.
    Results are ordered by entry_time descending.

    Args:
        start_date: Start date (inclusive) for filtering by trade_date.
        end_date: End date (inclusive) for filtering by trade_date.
        strategy_name: Filter by exact strategy name.

    Returns:
        List of matching PaperTrade records.
    """
    query = PaperTrade.query

    # Default to current date when no filters provided
    if start_date is None and end_date is None and strategy_name is None:
        today = date.today()
        query = query.filter(PaperTrade.trade_date == today)
    else:
        if start_date is not None:
            query = query.filter(PaperTrade.trade_date >= start_date)
        if end_date is not None:
            query = query.filter(PaperTrade.trade_date <= end_date)
        if strategy_name is not None:
            query = query.filter(PaperTrade.strategy_name == strategy_name)

    # Order by entry_time descending (NULLs last)
    query = query.order_by(PaperTrade.entry_time.desc())

    return query.all()


def get_distinct_strategies() -> list[str]:
    """Return distinct strategy names from the paper_trades table, ordered alphabetically."""
    results = (
        db_session.query(PaperTrade.strategy_name)
        .distinct()
        .order_by(PaperTrade.strategy_name)
        .all()
    )
    return [row[0] for row in results if row[0]]


def get_trade_summary(
    start_date=None, end_date=None, strategy_name=None
) -> dict:
    """Return aggregated trade statistics.

    Args:
        start_date: Start date (inclusive) for filtering.
        end_date: End date (inclusive) for filtering.
        strategy_name: Filter by exact strategy name.

    Returns:
        Dictionary with: total_trades, total_pnl, winning_trades,
        losing_trades, win_rate, and per_strategy breakdown.
    """
    trades = query_trades(
        start_date=start_date, end_date=end_date, strategy_name=strategy_name
    )

    total_trades = len(trades)
    trades_with_pnl = [t for t in trades if t.pnl is not None]
    winning_trades = sum(1 for t in trades_with_pnl if t.pnl > 0)
    losing_trades = sum(1 for t in trades_with_pnl if t.pnl < 0)
    total_pnl = sum(float(t.pnl) for t in trades_with_pnl)

    trades_with_pnl_count = len(trades_with_pnl)
    win_rate = (
        round((winning_trades / trades_with_pnl_count) * 100, 2)
        if trades_with_pnl_count > 0
        else 0.0
    )

    # Per-strategy breakdown
    per_strategy = {}
    for trade in trades:
        sname = trade.strategy_name
        if sname not in per_strategy:
            per_strategy[sname] = {
                "total_trades": 0,
                "total_pnl": 0.0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
            }
        per_strategy[sname]["total_trades"] += 1
        if trade.pnl is not None:
            pnl_val = float(trade.pnl)
            per_strategy[sname]["total_pnl"] += pnl_val
            if pnl_val > 0:
                per_strategy[sname]["winning_trades"] += 1
            elif pnl_val < 0:
                per_strategy[sname]["losing_trades"] += 1

    # Calculate win_rate per strategy
    for sname, stats in per_strategy.items():
        strategy_trades_with_pnl = stats["winning_trades"] + stats["losing_trades"]
        if strategy_trades_with_pnl > 0:
            stats["win_rate"] = round(
                (stats["winning_trades"] / strategy_trades_with_pnl) * 100, 2
            )

    return {
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 4),
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "per_strategy": per_strategy,
    }
