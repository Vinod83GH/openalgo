# test/test_paper_journal_api.py
"""Integration tests for the Paper Trade Journal REST API.

Tests the full trade lifecycle via the Flask test client:
- Create trade → update with exit → query → verify summary stats
- Authentication failure returns 401
- PATCH non-existent trade returns 404
- Date filtering returns correct subset
- Strategy filtering returns exact matches
- No-filter query defaults to today's trades
- Summary with no trades returns zeros
"""

import json
import os
import sys
from datetime import date, datetime
from unittest.mock import patch

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set environment variables before importing app modules
os.environ["DATABASE_URL"] = "sqlite:///test_paper_journal_api.db"
os.environ["TESTING"] = "true"

import database.paper_trade_db as ptdb
from blueprints.paper_journal import paper_journal_bp
from limiter import limiter


@pytest.fixture
def app():
    """Create a minimal Flask app with the paper_journal_bp blueprint registered."""
    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"

    # Disable rate limiting in tests
    limiter.init_app(app)
    limiter.enabled = False

    app.register_blueprint(paper_journal_bp)

    # Create database tables
    with app.app_context():
        ptdb.Base.metadata.create_all(bind=ptdb.engine)

    yield app

    # Cleanup
    ptdb.db_session.remove()
    ptdb.Base.metadata.drop_all(bind=ptdb.engine)


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def mock_auth():
    """Mock verify_api_key to return a user_id for 'test-key' and None otherwise."""
    def _verify(api_key):
        if api_key == "test-key":
            return 1  # Return a valid user_id
        return None

    with patch("blueprints.paper_journal.verify_api_key", side_effect=_verify) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Test: Full trade lifecycle (create → update → query → summary)
# ---------------------------------------------------------------------------


class TestFullTradeLifecycle:
    """End-to-end test: create trade → close with exit → query → verify summary."""

    def test_full_lifecycle(self, client, mock_auth):
        """Create a trade, close it with exit data, query it, and verify summary."""
        today = date.today()
        today_str = today.isoformat()

        # Step 1: POST /trade — create a new trade
        # Note: trade_date is passed as a date object via custom_metadata workaround,
        # or we set it directly. The service layer passes fields to create_trade as-is,
        # so we pre-seed trade_date by inserting directly for the query/summary steps.
        create_payload = {
            "apikey": "test-key",
            "strategy_name": "TestStrategy",
            "direction": "BULLISH",
            "entry_spot_price": 24150.50,
            "entry_option_symbol": "NIFTY15JAN25C24200",
            "entry_option_price": 185.00,
            "entry_quantity": 75,
            "entry_action": "BUY",
            "custom_metadata": {"first_candle_high": 24180, "bias": "BULLISH"},
        }

        resp = client.post(
            "/api/v1/paperjournal/trade",
            data=json.dumps(create_payload),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "success"
        trade_id = data["data"]["trade_id"]
        assert trade_id > 0

        # Set trade_date directly in DB so we can query by date
        ptdb.update_trade(trade_id, trade_date=today)

        # Step 2: PATCH /trade/<id> — close with exit data
        update_payload = {
            "apikey": "test-key",
            "exit_spot_price": 24050.25,
            "exit_option_price": 145.00,
            "exit_reason": "SL",
            "custom_metadata": {"sl_trigger_spot": 24050.25},
        }

        resp = client.patch(
            f"/api/v1/paperjournal/trade/{trade_id}",
            data=json.dumps(update_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        trade_data = data["data"]
        assert trade_data["trade_id"] == trade_id
        # P&L for BUY: (145 - 185) * 75 = -3000
        assert trade_data["pnl"] == -3000.0
        assert trade_data["exit_reason"] == "SL"
        # Verify metadata merge
        assert trade_data["custom_metadata"]["first_candle_high"] == 24180
        assert trade_data["custom_metadata"]["sl_trigger_spot"] == 24050.25

        # Step 3: GET /trades — query trades for today
        resp = client.get(
            f"/api/v1/paperjournal/trades?apikey=test-key&start_date={today_str}&end_date={today_str}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        trades = data["data"]
        assert len(trades) == 1
        assert trades[0]["trade_id"] == trade_id
        assert trades[0]["strategy_name"] == "TestStrategy"

        # Step 4: GET /summary — verify summary stats
        resp = client.get(
            f"/api/v1/paperjournal/summary?apikey=test-key&start_date={today_str}&end_date={today_str}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        summary = data["data"]
        assert summary["total_trades"] == 1
        assert summary["total_pnl"] == -3000.0
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 1
        assert summary["win_rate"] == 0.0
        assert "TestStrategy" in summary["per_strategy"]


# ---------------------------------------------------------------------------
# Test: Authentication failure returns 401
# ---------------------------------------------------------------------------


class TestAuthentication:
    """Test API key authentication on all endpoints."""

    def test_post_trade_invalid_key_returns_401(self, client, mock_auth):
        """POST /trade with invalid API key returns 401."""
        resp = client.post(
            "/api/v1/paperjournal/trade",
            data=json.dumps({"apikey": "invalid-key", "strategy_name": "Test"}),
            content_type="application/json",
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["status"] == "error"
        assert "Invalid API key" in data["message"]

    def test_patch_trade_invalid_key_returns_401(self, client, mock_auth):
        """PATCH /trade/<id> with invalid API key returns 401."""
        resp = client.patch(
            "/api/v1/paperjournal/trade/1",
            data=json.dumps({"apikey": "bad-key", "exit_reason": "SL"}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_get_trades_invalid_key_returns_401(self, client, mock_auth):
        """GET /trades with invalid API key returns 401."""
        resp = client.get("/api/v1/paperjournal/trades?apikey=wrong-key")
        assert resp.status_code == 401

    def test_get_summary_invalid_key_returns_401(self, client, mock_auth):
        """GET /summary with invalid API key returns 401."""
        resp = client.get("/api/v1/paperjournal/summary?apikey=wrong-key")
        assert resp.status_code == 401

    def test_post_trade_missing_key_returns_401(self, client, mock_auth):
        """POST /trade with no API key returns 401."""
        resp = client.post(
            "/api/v1/paperjournal/trade",
            data=json.dumps({"strategy_name": "Test"}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_get_trades_missing_key_returns_401(self, client, mock_auth):
        """GET /trades with no API key returns 401."""
        resp = client.get("/api/v1/paperjournal/trades")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test: PATCH non-existent trade returns 404
# ---------------------------------------------------------------------------


class TestTradeNotFound:
    """Test 404 behavior for non-existent trades."""

    def test_patch_nonexistent_trade_returns_404(self, client, mock_auth):
        """PATCH /trade/<id> for non-existent trade returns 404."""
        resp = client.patch(
            "/api/v1/paperjournal/trade/99999",
            data=json.dumps({"apikey": "test-key", "exit_reason": "SL"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["status"] == "error"
        assert "not found" in data["message"].lower()


# ---------------------------------------------------------------------------
# Test: Date filtering returns correct subset
# ---------------------------------------------------------------------------


class TestDateFiltering:
    """Test date range filtering on GET /trades."""

    def test_date_filtering_returns_correct_subset(self, client, mock_auth):
        """GET /trades with date range returns only trades in that range."""
        # Create trades on different dates directly in the database
        ptdb.create_trade(strategy_name="Day1", trade_date=date(2025, 1, 14))
        ptdb.create_trade(strategy_name="Day2", trade_date=date(2025, 1, 15))
        ptdb.create_trade(strategy_name="Day3", trade_date=date(2025, 1, 16))
        ptdb.create_trade(strategy_name="Day4", trade_date=date(2025, 1, 17))

        # Query only Jan 15-16
        resp = client.get(
            "/api/v1/paperjournal/trades?apikey=test-key&start_date=2025-01-15&end_date=2025-01-16"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        trades = data["data"]
        assert len(trades) == 2
        strategy_names = {t["strategy_name"] for t in trades}
        assert strategy_names == {"Day2", "Day3"}

    def test_start_date_only_filter(self, client, mock_auth):
        """GET /trades with only start_date returns trades from that date onward."""
        ptdb.create_trade(strategy_name="Early", trade_date=date(2025, 1, 10))
        ptdb.create_trade(strategy_name="Late", trade_date=date(2025, 1, 20))

        resp = client.get(
            "/api/v1/paperjournal/trades?apikey=test-key&start_date=2025-01-15"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        trades = data["data"]
        assert len(trades) == 1
        assert trades[0]["strategy_name"] == "Late"


# ---------------------------------------------------------------------------
# Test: Strategy filtering returns exact matches
# ---------------------------------------------------------------------------


class TestStrategyFiltering:
    """Test strategy_name filtering on GET /trades."""

    def test_strategy_filter_exact_match(self, client, mock_auth):
        """GET /trades with strategy_name returns only trades with that exact name."""
        ptdb.create_trade(
            strategy_name="AlphaStrategy", trade_date=date(2025, 1, 15)
        )
        ptdb.create_trade(
            strategy_name="BetaStrategy", trade_date=date(2025, 1, 15)
        )
        ptdb.create_trade(
            strategy_name="AlphaStrategy", trade_date=date(2025, 1, 15)
        )
        ptdb.create_trade(
            strategy_name="AlphaStrategyV2", trade_date=date(2025, 1, 15)
        )

        resp = client.get(
            "/api/v1/paperjournal/trades?apikey=test-key&strategy_name=AlphaStrategy"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        trades = data["data"]
        assert len(trades) == 2
        assert all(t["strategy_name"] == "AlphaStrategy" for t in trades)

    def test_strategy_filter_no_match(self, client, mock_auth):
        """GET /trades with non-existent strategy returns empty list."""
        ptdb.create_trade(
            strategy_name="RealStrategy", trade_date=date(2025, 1, 15)
        )

        resp = client.get(
            "/api/v1/paperjournal/trades?apikey=test-key&strategy_name=FakeStrategy"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        trades = data["data"]
        assert len(trades) == 0


# ---------------------------------------------------------------------------
# Test: No-filter query defaults to today's trades
# ---------------------------------------------------------------------------


class TestDefaultToday:
    """Test that GET /trades with no filters defaults to today's trades."""

    def test_no_filter_defaults_to_today(self, client, mock_auth):
        """GET /trades with no date/strategy filters returns only today's trades."""
        today = date.today()
        ptdb.create_trade(strategy_name="TodayTrade", trade_date=today)
        ptdb.create_trade(strategy_name="OldTrade", trade_date=date(2020, 1, 1))

        resp = client.get("/api/v1/paperjournal/trades?apikey=test-key")
        assert resp.status_code == 200
        data = resp.get_json()
        trades = data["data"]
        assert len(trades) == 1
        assert trades[0]["strategy_name"] == "TodayTrade"


# ---------------------------------------------------------------------------
# Test: Summary with no trades returns zeros
# ---------------------------------------------------------------------------


class TestSummaryNoTrades:
    """Test summary statistics when there are no trades."""

    def test_summary_no_trades_returns_zeros(self, client, mock_auth):
        """GET /summary with no matching trades returns zero statistics."""
        resp = client.get(
            "/api/v1/paperjournal/summary?apikey=test-key&start_date=2025-01-15&end_date=2025-01-15"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        summary = data["data"]
        assert summary["total_trades"] == 0
        assert summary["total_pnl"] == 0
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 0
        assert summary["win_rate"] == 0.0
        assert summary["per_strategy"] == {}
