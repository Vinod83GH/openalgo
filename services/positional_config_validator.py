# services/positional_config_validator.py

from datetime import datetime

from utils.logging import get_logger

logger = get_logger(__name__)

# Allowed candle timeframe values (in minutes)
ALLOWED_CANDLE_TIMEFRAMES = {1, 2, 3, 5, 10, 15, 20, 30, 60}

# Valid strategy types
VALID_STRATEGY_TYPES = {"intraday", "positional"}

# Datetime format expected: YYYY-MM-DD HH:MM (24-hour, IST assumed)
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def _parse_datetime(value: str, field_name: str) -> tuple[datetime | None, str | None]:
    """Parse a datetime string in YYYY-MM-DD HH:MM format.

    Returns (parsed_datetime, None) on success, or (None, error_message) on failure.
    """
    if not value or not value.strip():
        return None, f"{field_name} is missing or empty"

    value = value.strip()
    try:
        parsed = datetime.strptime(value, DATETIME_FORMAT)
        return parsed, None
    except ValueError:
        return None, (
            f"{field_name} has invalid format: '{value}'. "
            f"Expected format: YYYY-MM-DD HH:MM (24-hour)"
        )


def validate_positional_config(env_vars: dict) -> tuple[bool, str | None]:
    """Validate positional strategy configuration environment variables.

    Args:
        env_vars: Dictionary of strategy environment variables.

    Returns:
        (True, None) if all validations pass.
        (False, error_message) if any validation fails, with a specific
        error message identifying which field or constraint failed.
    """
    # 1. Validate strategy_type
    strategy_type = env_vars.get("strategy_type", "").strip().lower()
    if strategy_type not in VALID_STRATEGY_TYPES:
        error = (
            f"strategy_type '{env_vars.get('strategy_type', '')}' is invalid. "
            f"Must be one of: {sorted(VALID_STRATEGY_TYPES)}"
        )
        logger.error(error)
        return False, error

    # 2. Validate CANDLE_TIMEFRAME_MIN
    candle_tf_raw = env_vars.get("CANDLE_TIMEFRAME_MIN", "")
    if candle_tf_raw is None or str(candle_tf_raw).strip() == "":
        # Default to 15 when absent or empty — this is valid, not an error
        env_vars["CANDLE_TIMEFRAME_MIN"] = "15"
    else:
        candle_tf_str = str(candle_tf_raw).strip()
        try:
            candle_tf = int(candle_tf_str)
        except (ValueError, TypeError):
            error = (
                f"CANDLE_TIMEFRAME_MIN has invalid value: '{candle_tf_str}'. "
                f"Must be an integer in {sorted(ALLOWED_CANDLE_TIMEFRAMES)}"
            )
            logger.error(error)
            return False, error

        if candle_tf not in ALLOWED_CANDLE_TIMEFRAMES:
            error = (
                f"CANDLE_TIMEFRAME_MIN value {candle_tf} is not allowed. "
                f"Must be one of: {sorted(ALLOWED_CANDLE_TIMEFRAMES)}"
            )
            logger.error(error)
            return False, error

    # For intraday strategies, datetime and product validations are not required
    if strategy_type == "intraday":
        return True, None

    # --- Positional-specific validations below ---

    # 3. Default STRATEGY_PRODUCT to "NRML" for positional strategies
    if not env_vars.get("STRATEGY_PRODUCT", "").strip():
        env_vars["STRATEGY_PRODUCT"] = "NRML"

    # 4. Validate datetime fields
    entry_start_raw = env_vars.get("STRATEGY_ENTRY_START_DATE_TIME", "")
    entry_end_raw = env_vars.get("STRATEGY_ENTRY_END_DATE_TIME", "")
    exit_dt_raw = env_vars.get("STRATEGY_EXIT_DATE_TIME", "")

    entry_start, err = _parse_datetime(entry_start_raw, "STRATEGY_ENTRY_START_DATE_TIME")
    if err:
        logger.error(err)
        return False, err

    entry_end, err = _parse_datetime(entry_end_raw, "STRATEGY_ENTRY_END_DATE_TIME")
    if err:
        logger.error(err)
        return False, err

    exit_dt, err = _parse_datetime(exit_dt_raw, "STRATEGY_EXIT_DATE_TIME")
    if err:
        logger.error(err)
        return False, err

    # 5. Validate chronological ordering: entry_start < entry_end < exit_dt
    if entry_start >= entry_end:
        error = (
            f"Chronological ordering violated: STRATEGY_ENTRY_START_DATE_TIME "
            f"({entry_start_raw.strip()}) must be before "
            f"STRATEGY_ENTRY_END_DATE_TIME ({entry_end_raw.strip()})"
        )
        logger.error(error)
        return False, error

    if entry_end >= exit_dt:
        error = (
            f"Chronological ordering violated: STRATEGY_ENTRY_END_DATE_TIME "
            f"({entry_end_raw.strip()}) must be before "
            f"STRATEGY_EXIT_DATE_TIME ({exit_dt_raw.strip()})"
        )
        logger.error(error)
        return False, error

    return True, None
