# services/kill_switch_service.py

from typing import Protocol

from database.kill_switch_db import (
    get_kill_switch_config,
    invalidate_kill_switch_cache,
    update_kill_switch_status_cache,
    upsert_kill_switch_config,
)
from utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# KillSwitchAdapter protocol
# ---------------------------------------------------------------------------

class KillSwitchAdapter(Protocol):
    def get_kill_switch_status(self, access_token: str) -> str:
        """Returns 'ACTIVATED' or 'DEACTIVATED'."""
        ...

    def activate_kill_switch(self, access_token: str) -> dict:
        """Calls broker ACTIVATE API. Returns broker response."""
        ...

    def set_pnl_exit(self, access_token: str, profit_threshold: float, loss_threshold: float) -> dict:
        """Registers P&L thresholds with broker. Returns broker response."""
        ...


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------

class _DhanAdapter:
    """Thin wrapper that satisfies KillSwitchAdapter for the Dhan broker."""

    def get_kill_switch_status(self, access_token: str) -> str:
        from broker.dhan.api.kill_switch_api import get_kill_switch_status
        return get_kill_switch_status(access_token)

    def activate_kill_switch(self, access_token: str) -> dict:
        from broker.dhan.api.kill_switch_api import activate_kill_switch
        return activate_kill_switch(access_token)

    def set_pnl_exit(self, access_token: str, profit_threshold: float, loss_threshold: float) -> dict:
        from broker.dhan.api.kill_switch_api import set_pnl_exit
        return set_pnl_exit(access_token, profit_threshold, loss_threshold)


def _get_adapter(broker: str) -> KillSwitchAdapter:
    """Return the correct KillSwitchAdapter instance for the given broker name."""
    if broker.lower() == "dhan":
        return _DhanAdapter()
    raise NotImplementedError(
        f"No KillSwitchAdapter registered for broker '{broker}'. "
        "Implement a KillSwitchAdapter in broker/{broker}/api/kill_switch_api.py "
        "and register it in _get_adapter()."
    )


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def get_kill_switch_status(broker_name: str, auth_token: str, broker: str) -> dict:
    """Return the full kill switch status dict for the given broker session.

    Calls the broker adapter to get the live status, updates the local cache,
    then fetches the current P&L from the position book.

    Returns a dict with keys:
        broker_name, enabled, profit_threshold, loss_threshold,
        kill_switch_status, current_pnl
    """
    adapter = _get_adapter(broker)

    # Fetch live status from broker and sync to local cache
    try:
        live_status = adapter.get_kill_switch_status(auth_token)
        update_kill_switch_status_cache(broker_name, live_status)
    except Exception as e:
        logger.warning(f"Kill switch: failed to fetch live status for {broker_name}: {e}")
        live_status = None

    config = get_kill_switch_config(broker_name)
    if live_status is None:
        live_status = config.kill_switch_status

    # Fetch current P&L from position book
    current_pnl = 0.0
    try:
        from services.positionbook_service import get_positionbook
        success, response, _ = get_positionbook(auth_token=auth_token, broker=broker)
        if success and response.get("status") == "success":
            positions = response.get("data", [])
            current_pnl = sum(float(p.get("pnl", 0)) for p in positions)
    except Exception as e:
        logger.warning(f"Kill switch: failed to fetch P&L for {broker_name}: {e}")

    return {
        "broker_name": broker_name,
        "enabled": config.enabled,
        "profit_threshold": float(config.profit_threshold),
        "loss_threshold": float(config.loss_threshold),
        "kill_switch_status": live_status,
        "current_pnl": round(current_pnl, 2),
    }


def update_kill_switch_config(
    broker_name: str,
    enabled: bool,
    profit_threshold: float,
    loss_threshold: float,
    auth_token: str,
    broker: str,
) -> dict:
    """Validate thresholds, persist config, call broker pnlExit, invalidate cache.

    Raises ValueError if thresholds are negative.
    Returns the updated config dict.
    """
    if float(profit_threshold) < 0 or float(loss_threshold) < 0:
        raise ValueError(
            "profit_threshold and loss_threshold must be non-negative numbers"
        )

    upsert_kill_switch_config(
        broker_name,
        enabled=enabled,
        profit_threshold=profit_threshold,
        loss_threshold=loss_threshold,
    )

    # Register thresholds with broker so it can monitor independently
    adapter = _get_adapter(broker)
    try:
        adapter.set_pnl_exit(auth_token, float(profit_threshold), float(loss_threshold))
    except Exception as e:
        logger.warning(
            f"Kill switch: pnlExit call failed for {broker_name}: {e}. "
            "Local config was saved."
        )
        raise

    invalidate_kill_switch_cache(broker_name)

    config = get_kill_switch_config(broker_name)
    return {
        "broker_name": broker_name,
        "enabled": config.enabled,
        "profit_threshold": float(config.profit_threshold),
        "loss_threshold": float(config.loss_threshold),
        "kill_switch_status": config.kill_switch_status,
    }


def activate_kill_switch(broker_name: str, auth_token: str, broker: str) -> dict:
    """Call broker ACTIVATE API and update local status cache to 'ACTIVATED'.

    Returns the broker response dict.
    """
    adapter = _get_adapter(broker)
    response = adapter.activate_kill_switch(auth_token)

    # Update local cache to reflect activated state immediately
    update_kill_switch_status_cache(broker_name, "ACTIVATED")

    return response


def get_broker_kill_switch_status(broker_name: str, auth_token: str, broker: str) -> str:
    """Fetch live kill switch status from broker, update local cache, return status string."""
    adapter = _get_adapter(broker)
    status = adapter.get_kill_switch_status(auth_token)
    update_kill_switch_status_cache(broker_name, status)
    return status


def evaluate_pnl_thresholds(
    broker_name: str, current_pnl: float, auth_token: str, broker: str
) -> bool:
    """Evaluate P&L against configured thresholds and activate kill switch if breached.

    Skips evaluation when:
    - Kill switch is not enabled
    - The relevant threshold is 0 (disabled)

    Profit breach: current_pnl >= profit_threshold (when profit_threshold > 0)
    Loss breach:   current_pnl <= -loss_threshold  (when loss_threshold > 0)

    Logs a structured warning on breach. Returns True if activation was triggered.
    """
    config = get_kill_switch_config(broker_name)

    if not config.enabled:
        return False

    profit_threshold = float(config.profit_threshold)
    loss_threshold = float(config.loss_threshold)

    # Check profit-side breach
    if profit_threshold > 0 and current_pnl >= profit_threshold:
        logger.warning(
            "Kill switch threshold breached",
            extra={
                "direction": "profit",
                "threshold": profit_threshold,
                "actual_pnl": current_pnl,
                "broker_name": broker_name,
            },
        )
        activate_kill_switch(broker_name, auth_token, broker)
        return True

    # Check loss-side breach
    if loss_threshold > 0 and current_pnl <= -loss_threshold:
        logger.warning(
            "Kill switch threshold breached",
            extra={
                "direction": "loss",
                "threshold": loss_threshold,
                "actual_pnl": current_pnl,
                "broker_name": broker_name,
            },
        )
        activate_kill_switch(broker_name, auth_token, broker)
        return True

    return False
