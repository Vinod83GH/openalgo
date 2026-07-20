# services/paper_trade_journal_service.py

import json

from database.paper_trade_db import (
    create_trade,
    get_distinct_strategies,
    get_trade,
    get_trade_summary,
    query_trades,
    update_trade,
)
from database.settings_db import get_analyze_mode
from utils.logging import get_logger

logger = get_logger(__name__)

# Valid enum values for optional validation
VALID_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
VALID_ENTRY_ACTIONS = {"BUY", "SELL"}


def list_strategies() -> list[str]:
    """Return all distinct strategy names."""
    return get_distinct_strategies()


def open_trade(trade_data: dict) -> dict:
    """Open a new trade record.

    Validates optional enum fields (direction, entry_action), serializes
    custom_metadata to JSON string if present, and creates the trade.

    Args:
        trade_data: Dictionary of trade fields.

    Returns:
        Success dict with trade_id, or error dict.
    """
    # strategy_name is required
    if not trade_data.get("strategy_name"):
        return {"status": "error", "message": "strategy_name is required"}

    # Validate direction if provided
    direction = trade_data.get("direction")
    if direction is not None and direction not in VALID_DIRECTIONS:
        return {
            "status": "error",
            "message": f"Invalid direction '{direction}'. Must be one of: {', '.join(sorted(VALID_DIRECTIONS))}",
        }

    # Validate entry_action if provided
    entry_action = trade_data.get("entry_action")
    if entry_action is not None and entry_action not in VALID_ENTRY_ACTIONS:
        return {
            "status": "error",
            "message": f"Invalid entry_action '{entry_action}'. Must be one of: {', '.join(sorted(VALID_ENTRY_ACTIONS))}",
        }

    # Serialize custom_metadata to JSON string if present
    fields = dict(trade_data)
    if "custom_metadata" in fields and fields["custom_metadata"] is not None:
        if isinstance(fields["custom_metadata"], dict):
            fields["custom_metadata"] = json.dumps(fields["custom_metadata"])

    # Convert trade_date string to date object if needed
    if "trade_date" in fields and fields["trade_date"] is not None:
        if isinstance(fields["trade_date"], str):
            from datetime import datetime as dt
            try:
                fields["trade_date"] = dt.strptime(fields["trade_date"], "%Y-%m-%d").date()
            except ValueError:
                fields["trade_date"] = None

    # Convert entry_time/exit_time strings to datetime objects if needed
    for time_field in ("entry_time", "exit_time"):
        if time_field in fields and fields[time_field] is not None:
            if isinstance(fields[time_field], str):
                from datetime import datetime as dt
                try:
                    # Handle ISO format with timezone info
                    fields[time_field] = dt.fromisoformat(fields[time_field])
                except ValueError:
                    try:
                        fields[time_field] = dt.strptime(fields[time_field], "%Y-%m-%dT%H:%M:%S")
                    except ValueError:
                        fields[time_field] = None

    trade = create_trade(**fields)
    return {"status": "success", "data": {"trade_id": trade.id}}


def close_trade(trade_id: int, update_data: dict) -> dict:
    """Close or update an existing trade.

    Fetches the trade (returns error if not found), merges custom_metadata
    (shallow merge), calculates P&L when entry_option_price, exit_option_price,
    and entry_quantity are all present, then persists the update.

    Args:
        trade_id: The ID of the trade to update.
        update_data: Dictionary of fields to update.

    Returns:
        Success dict with updated trade data, or error dict.
    """
    trade = get_trade(trade_id)
    if trade is None:
        return {"status": "error", "message": "Trade not found"}

    fields = dict(update_data)

    # Handle custom_metadata merge
    if "custom_metadata" in fields and fields["custom_metadata"] is not None:
        new_metadata = fields["custom_metadata"]
        if isinstance(new_metadata, str):
            try:
                new_metadata = json.loads(new_metadata)
            except (json.JSONDecodeError, TypeError):
                new_metadata = {}

        # Load existing metadata
        existing_metadata = {}
        if trade.custom_metadata:
            try:
                existing_metadata = json.loads(trade.custom_metadata)
            except (json.JSONDecodeError, TypeError):
                existing_metadata = {}

        # Shallow merge: existing keys overwritten by new keys
        merged = {**existing_metadata, **new_metadata}
        fields["custom_metadata"] = json.dumps(merged)
    elif "custom_metadata" in fields and fields["custom_metadata"] is None:
        # Explicitly setting metadata to None
        fields["custom_metadata"] = None

    # Calculate P&L if all required fields are present
    # Determine entry values (from existing trade or update)
    entry_option_price = (
        float(trade.entry_option_price) if trade.entry_option_price is not None else None
    )
    exit_option_price = fields.get("exit_option_price")
    if exit_option_price is None and trade.exit_option_price is not None:
        exit_option_price = float(trade.exit_option_price)
    elif exit_option_price is not None:
        exit_option_price = float(exit_option_price)

    entry_quantity = (
        int(trade.entry_quantity) if trade.entry_quantity is not None else None
    )
    entry_action = trade.entry_action

    # Calculate P&L only when all three fields are available
    if (
        entry_option_price is not None
        and exit_option_price is not None
        and entry_quantity is not None
    ):
        if entry_action == "BUY":
            pnl = (exit_option_price - entry_option_price) * entry_quantity
        elif entry_action == "SELL":
            pnl = (entry_option_price - exit_option_price) * entry_quantity
        else:
            # No valid entry_action, leave pnl as None
            pnl = None

        if pnl is not None:
            fields["pnl"] = round(pnl, 4)

    # Convert exit_time string to datetime object if needed
    if "exit_time" in fields and fields["exit_time"] is not None:
        if isinstance(fields["exit_time"], str):
            from datetime import datetime as dt
            try:
                fields["exit_time"] = dt.fromisoformat(fields["exit_time"])
            except ValueError:
                try:
                    fields["exit_time"] = dt.strptime(fields["exit_time"], "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    fields["exit_time"] = None

    updated_trade = update_trade(trade_id, **fields)
    return {"status": "success", "data": _trade_to_dict(updated_trade)}


def list_trades(start_date=None, end_date=None, strategy_name=None) -> list[dict]:
    """List trades with optional filters.

    Delegates to query_trades and serializes each PaperTrade to a dict.

    Args:
        start_date: Start date filter (inclusive).
        end_date: End date filter (inclusive).
        strategy_name: Filter by exact strategy name.

    Returns:
        List of trade dictionaries.
    """
    trades = query_trades(
        start_date=start_date, end_date=end_date, strategy_name=strategy_name
    )
    return [_trade_to_dict(trade) for trade in trades]


def get_summary(start_date=None, end_date=None, strategy_name=None) -> dict:
    """Get trade summary statistics.

    Calls get_trade_summary and returns the formatted summary dict
    with per_strategy breakdown.

    Args:
        start_date: Start date filter (inclusive).
        end_date: End date filter (inclusive).
        strategy_name: Filter by exact strategy name.

    Returns:
        Summary dictionary with aggregated stats.
    """
    return get_trade_summary(
        start_date=start_date, end_date=end_date, strategy_name=strategy_name
    )


def get_journal_status() -> dict:
    """Check if the application is in analyze mode.

    Calls get_analyze_mode() from database/settings_db.py to determine
    the current mode.

    Returns:
        Dictionary with mode ("analyze" or "live") and journal_active flag.
    """
    is_analyze = get_analyze_mode()
    mode = "analyze" if is_analyze else "live"
    return {"mode": mode, "journal_active": is_analyze}


def _trade_to_dict(trade) -> dict:
    """Serialize a PaperTrade instance to a dictionary.

    Deserializes custom_metadata from JSON string back to dict.
    """
    # Parse custom_metadata from JSON
    custom_metadata = None
    if trade.custom_metadata:
        try:
            custom_metadata = json.loads(trade.custom_metadata)
        except (json.JSONDecodeError, TypeError):
            # If deserialization fails, return raw string
            custom_metadata = trade.custom_metadata

    return {
        "trade_id": trade.id,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        "trade_date": trade.trade_date.isoformat() if trade.trade_date else None,
        "strategy_name": trade.strategy_name,
        "direction": trade.direction,
        "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
        "entry_spot_price": float(trade.entry_spot_price) if trade.entry_spot_price is not None else None,
        "entry_option_symbol": trade.entry_option_symbol,
        "entry_option_price": float(trade.entry_option_price) if trade.entry_option_price is not None else None,
        "entry_quantity": trade.entry_quantity,
        "entry_action": trade.entry_action,
        "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
        "exit_spot_price": float(trade.exit_spot_price) if trade.exit_spot_price is not None else None,
        "exit_option_price": float(trade.exit_option_price) if trade.exit_option_price is not None else None,
        "exit_reason": trade.exit_reason,
        "pnl": float(trade.pnl) if trade.pnl is not None else None,
        "custom_metadata": custom_metadata,
    }
