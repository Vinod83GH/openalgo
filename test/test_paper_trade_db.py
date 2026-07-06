# test/test_paper_trade_db.py
"""Unit tests for database/paper_trade_db.py CRUD operations."""

import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Must set DATABASE_URL before importing the module
os.environ["DATABASE_URL"] = "sqlite:///test_paper_trade.db"

import database.paper_trade_db as ptdb


@pytest.fixture(autouse=True)
def fresh_db():
    """Create tables, yield, then drop all and clean up."""
    ptdb.Base.metadata.create_all(bind=ptdb.engine)
    yield
    ptdb.db_session.remove()
    ptdb.Base.metadata.drop_all(bind=ptdb.engine)


def test_create_trade_minimal():
    """Create a trade with only strategy_name (all other columns nullable)."""
    trade = ptdb.create_trade(strategy_name="TestStrategy")
    assert trade.id > 0
    assert trade.strategy_name == "TestStrategy"
    assert trade.direction is None
    assert trade.entry_option_price is None
    assert trade.pnl is None


def test_create_trade_all_fields():
    """Create a trade with all fields populated."""
    trade = ptdb.create_trade(
        strategy_name="FullTrade",
        trade_date=date(2025, 1, 15),
        direction="BULLISH",
        entry_time=datetime(2025, 1, 15, 9, 16, 5),
        entry_spot_price=Decimal("24150.5000"),
        entry_option_symbol="NIFTY15JAN25C24200",
        entry_option_price=Decimal("185.0000"),
        entry_quantity=75,
        entry_action="BUY",
        exit_time=datetime(2025, 1, 15, 10, 45, 0),
        exit_spot_price=Decimal("24050.2500"),
        exit_option_price=Decimal("145.0000"),
        exit_reason="SL",
        pnl=Decimal("-3000.0000"),
        custom_metadata=json.dumps({"candle_high": 24180}),
    )
    assert trade.id > 0
    assert trade.trade_date == date(2025, 1, 15)
    assert trade.direction == "BULLISH"
    assert float(trade.entry_option_price) == 185.0


def test_get_trade_found():
    """get_trade returns the trade when it exists."""
    trade = ptdb.create_trade(strategy_name="GetTest")
    fetched = ptdb.get_trade(trade.id)
    assert fetched is not None
    assert fetched.strategy_name == "GetTest"


def test_get_trade_not_found():
    """get_trade returns None for non-existent ID."""
    assert ptdb.get_trade(9999) is None


def test_update_trade_success():
    """update_trade updates fields and returns updated trade."""
    trade = ptdb.create_trade(strategy_name="UpdateTest", direction="BULLISH")
    updated = ptdb.update_trade(trade.id, exit_reason="TARGET", pnl=Decimal("500.0000"))
    assert updated is not None
    assert updated.exit_reason == "TARGET"
    assert float(updated.pnl) == 500.0
    # Original fields preserved
    assert updated.direction == "BULLISH"


def test_update_trade_not_found():
    """update_trade returns None for non-existent ID."""
    assert ptdb.update_trade(9999, exit_reason="SL") is None


def test_query_trades_date_filter():
    """query_trades filters by date range correctly."""
    ptdb.create_trade(strategy_name="S1", trade_date=date(2025, 1, 14))
    ptdb.create_trade(strategy_name="S2", trade_date=date(2025, 1, 15))
    ptdb.create_trade(strategy_name="S3", trade_date=date(2025, 1, 16))

    trades = ptdb.query_trades(start_date=date(2025, 1, 15), end_date=date(2025, 1, 15))
    assert len(trades) == 1
    assert trades[0].strategy_name == "S2"


def test_query_trades_strategy_filter():
    """query_trades filters by strategy_name correctly."""
    ptdb.create_trade(strategy_name="Alpha", trade_date=date(2025, 1, 15))
    ptdb.create_trade(strategy_name="Beta", trade_date=date(2025, 1, 15))
    ptdb.create_trade(strategy_name="Alpha", trade_date=date(2025, 1, 15))

    trades = ptdb.query_trades(strategy_name="Alpha")
    assert len(trades) == 2
    assert all(t.strategy_name == "Alpha" for t in trades)


def test_query_trades_default_today():
    """query_trades with no filters defaults to current date."""
    today = date.today()
    ptdb.create_trade(strategy_name="Today", trade_date=today)
    ptdb.create_trade(strategy_name="Yesterday", trade_date=date(2020, 1, 1))

    trades = ptdb.query_trades()
    assert len(trades) == 1
    assert trades[0].strategy_name == "Today"


def test_query_trades_order_by_entry_time():
    """query_trades orders by entry_time descending."""
    ptdb.create_trade(
        strategy_name="S1", trade_date=date(2025, 1, 15),
        entry_time=datetime(2025, 1, 15, 9, 0, 0)
    )
    ptdb.create_trade(
        strategy_name="S2", trade_date=date(2025, 1, 15),
        entry_time=datetime(2025, 1, 15, 11, 0, 0)
    )
    ptdb.create_trade(
        strategy_name="S3", trade_date=date(2025, 1, 15),
        entry_time=datetime(2025, 1, 15, 10, 0, 0)
    )

    trades = ptdb.query_trades(start_date=date(2025, 1, 15), end_date=date(2025, 1, 15))
    assert trades[0].strategy_name == "S2"  # 11:00
    assert trades[1].strategy_name == "S3"  # 10:00
    assert trades[2].strategy_name == "S1"  # 9:00


def test_get_trade_summary():
    """get_trade_summary returns correct aggregated statistics."""
    ptdb.create_trade(strategy_name="S1", trade_date=date(2025, 1, 15), pnl=Decimal("500.0000"))
    ptdb.create_trade(strategy_name="S1", trade_date=date(2025, 1, 15), pnl=Decimal("-200.0000"))
    ptdb.create_trade(strategy_name="S2", trade_date=date(2025, 1, 15), pnl=Decimal("300.0000"))
    ptdb.create_trade(strategy_name="S2", trade_date=date(2025, 1, 15))  # No PnL

    summary = ptdb.get_trade_summary(start_date=date(2025, 1, 15), end_date=date(2025, 1, 15))
    assert summary["total_trades"] == 4
    assert summary["total_pnl"] == 600.0
    assert summary["winning_trades"] == 2
    assert summary["losing_trades"] == 1
    assert summary["win_rate"] == round((2 / 3) * 100, 2)
    assert "S1" in summary["per_strategy"]
    assert "S2" in summary["per_strategy"]
    assert summary["per_strategy"]["S1"]["total_trades"] == 2
    assert summary["per_strategy"]["S2"]["total_trades"] == 2


def test_get_trade_summary_no_trades():
    """get_trade_summary with no trades returns zero values."""
    summary = ptdb.get_trade_summary(start_date=date(2025, 1, 15), end_date=date(2025, 1, 15))
    assert summary["total_trades"] == 0
    assert summary["total_pnl"] == 0
    assert summary["winning_trades"] == 0
    assert summary["losing_trades"] == 0
    assert summary["win_rate"] == 0.0
    assert summary["per_strategy"] == {}
