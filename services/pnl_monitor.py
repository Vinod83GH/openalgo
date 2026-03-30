# services/pnl_monitor.py

import threading
import time as time_module
from datetime import datetime
from time import sleep
from datetime import time

import pytz

from utils.logging import get_logger

logger = get_logger(__name__)


class PnLMonitor(threading.Thread):
    """Background daemon thread that polls broker kill switch status and evaluates P&L thresholds.

    Polls every POLL_INTERVAL_SECONDS during market hours (09:15–15:30 IST).
    The broker owns deactivation state — this monitor only calls ACTIVATE when thresholds
    are breached. No daily reset logic is needed; the broker resets automatically.
    """

    POLL_INTERVAL_SECONDS = 55
    MARKET_OPEN = time(9, 15)   # IST
    MARKET_CLOSE = time(15, 30)  # IST

    def __init__(self, **kwargs):
        super().__init__(daemon=True, **kwargs)
        self._tz = pytz.timezone("Asia/Kolkata")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_market_hours(self) -> bool:
        """Return True only when the current IST time is between 09:15 and 15:30 (exclusive)."""
        now_ist = datetime.now(self._tz).time()
        return self.MARKET_OPEN <= now_ist < self.MARKET_CLOSE

    def _compute_pnl(self, positions: list[dict]) -> float:
        """Sum the 'pnl' field across all position records."""
        return sum(float(p.get("pnl", 0)) for p in positions)

    def _get_auth_token_for_broker(self, broker_name: str):
        """Look up the active (non-revoked) auth token for the given broker name.

        Returns the decrypted auth token string, or None if no active session exists.
        """
        try:
            from database.auth_db import Auth, decrypt_token

            auth_obj = Auth.query.filter_by(broker=broker_name, is_revoked=False).first()
            if auth_obj is None:
                logger.debug(
                    f"PnL monitor: no active session for broker '{broker_name}', skipping."
                )
                return None
            return decrypt_token(auth_obj.auth)
        except Exception as e:
            logger.debug(
                f"PnL monitor: could not retrieve auth token for broker '{broker_name}': {e}"
            )
            return None

    def _poll_all_active_brokers(self) -> None:
        """Query all enabled KillSwitchConfig records and evaluate P&L thresholds for each."""
        # Deferred imports to avoid circular dependencies at module load time.
        # Import at call-site so tests can patch the module-level names.
        import database.kill_switch_db as _ks_db
        import services.kill_switch_service as _ks_svc
        import services.positionbook_service as _pos_svc

        KillSwitchConfig = _ks_db.KillSwitchConfig
        get_broker_kill_switch_status = _ks_svc.get_broker_kill_switch_status
        evaluate_pnl_thresholds = _ks_svc.evaluate_pnl_thresholds
        get_positionbook = _pos_svc.get_positionbook

        try:
            configs = KillSwitchConfig.query.filter_by(enabled=True).all()
        except Exception as e:
            logger.warning(f"PnL monitor: failed to query KillSwitchConfig records: {e}")
            return

        for config in configs:
            broker_name = config.broker_name
            try:
                # Resolve auth token for this broker
                auth_token = self._get_auth_token_for_broker(broker_name)
                if auth_token is None:
                    continue

                # 1. Update local kill switch status cache from broker API
                status = get_broker_kill_switch_status(
                    broker_name=broker_name,
                    auth_token=auth_token,
                    broker=broker_name,
                )

                # 2. Only evaluate P&L when broker is DEACTIVATED (not yet triggered)
                if status != "DEACTIVATED":
                    continue

                # 3. Fetch positions from broker
                success, response, _ = get_positionbook(
                    auth_token=auth_token, broker=broker_name
                )
                if not success or response.get("status") != "success":
                    logger.warning(
                        f"PnL monitor: position book API error for broker '{broker_name}': "
                        f"{response.get('message', 'unknown error')}"
                    )
                    continue

                positions = response.get("data", [])
                current_pnl = self._compute_pnl(positions)

                # 4. Evaluate thresholds — activates kill switch if breached
                evaluate_pnl_thresholds(
                    broker_name=broker_name,
                    current_pnl=current_pnl,
                    auth_token=auth_token,
                    broker=broker_name,
                )

            except Exception as e:
                logger.warning(
                    f"PnL monitor: error processing broker '{broker_name}': {e}"
                )

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Main loop: poll all active brokers during market hours, sleep between cycles."""
        logger.info("PnL monitor thread started.")
        while True:
            try:
                if self._is_market_hours():
                    self._poll_all_active_brokers()
            except Exception as e:
                # Catch-all so the thread never crashes
                logger.exception(f"PnL monitor: unexpected error in main loop: {e}")

            sleep(self.POLL_INTERVAL_SECONDS)
