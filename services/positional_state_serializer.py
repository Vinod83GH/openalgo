# services/positional_state_serializer.py
"""
State Serializer for Positional Strategy Hosting.

Handles explicit field mapping for StrategyState ↔ JSON key-value format.
- Type preservation: int stays int, bool stays bool, None stays None
- Float precision: 6 decimal places
- Validation on deserialization (missing fields, type mismatches)
- Schema version migration support
"""

import json
from dataclasses import dataclass, fields, asdict
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

# Current schema version
CURRENT_SCHEMA_VERSION = 1

# Float precision for serialization
FLOAT_PRECISION = 6


class StateValidationError(Exception):
    """Raised when state deserialization fails due to missing or invalid fields."""

    def __init__(self, message: str, invalid_fields: list[str] | None = None):
        self.invalid_fields = invalid_fields or []
        super().__init__(message)


@dataclass
class StrategyState:
    """Runtime state object for a positional trading strategy.

    All fields that represent a strategy's current status — including candle data,
    bias, entry status, position details, stop-loss levels, and trailing parameters.
    """

    # Metadata
    schema_version: int
    strategy_id: str
    timestamp: str  # ISO 8601

    # Candle data
    first_candle_high: float | None
    first_candle_low: float | None
    first_candle_close: float | None
    first_candle_mid: float | None

    # Trade state
    bias: str | None  # "BULLISH" | "BEARISH" | None
    entry_done: bool
    exit_done: bool
    option_symbol: str | None
    option_exchange: str | None
    actual_quantity: int | None
    entry_option_price_saved: float | None
    journal_trade_id: int | None
    sl_count: int
    cumulative_loss_pct: float
    high_watermark: float | None
    trailing_active: bool

    # Configuration snapshot
    config: dict  # All active STRATEGY_* values


# Field type definitions for validation and type coercion
# Maps field name → (expected_type, nullable)
_FIELD_SPECS: dict[str, tuple[type, bool]] = {
    "schema_version": (int, False),
    "strategy_id": (str, False),
    "timestamp": (str, False),
    "first_candle_high": (float, True),
    "first_candle_low": (float, True),
    "first_candle_close": (float, True),
    "first_candle_mid": (float, True),
    "bias": (str, True),
    "entry_done": (bool, False),
    "exit_done": (bool, False),
    "option_symbol": (str, True),
    "option_exchange": (str, True),
    "actual_quantity": (int, True),
    "entry_option_price_saved": (float, True),
    "journal_trade_id": (int, True),
    "sl_count": (int, False),
    "cumulative_loss_pct": (float, False),
    "high_watermark": (float, True),
    "trailing_active": (bool, False),
    "config": (dict, False),
}

# All required state keys (fields of StrategyState)
REQUIRED_STATE_KEYS = set(_FIELD_SPECS.keys())


def _round_float(value: float | None) -> float | None:
    """Round a float to the configured precision, preserving None."""
    if value is None:
        return None
    return round(value, FLOAT_PRECISION)


def _serialize_value(field_name: str, value: Any) -> str:
    """Serialize a single field value to a JSON string.

    Float values are rounded to 6 decimal places.
    """
    expected_type, nullable = _FIELD_SPECS[field_name]

    if value is None:
        return json.dumps(None)

    if expected_type == float:
        value = _round_float(value)

    return json.dumps(value)


def serialize_state(state: StrategyState) -> dict[str, str]:
    """Convert a StrategyState to dict of {state_key: json_string} for DB storage.

    Each field is explicitly mapped and serialized as a JSON-encoded string.
    Float values are rounded to 6 decimal places.

    Args:
        state: The StrategyState object to serialize.

    Returns:
        Dictionary where keys are state field names and values are JSON-encoded strings.
    """
    result: dict[str, str] = {}

    for field in fields(state):
        field_name = field.name
        value = getattr(state, field_name)
        result[field_name] = _serialize_value(field_name, value)

    logger.debug(
        f"StateSerializer: Serialized state for strategy '{state.strategy_id}' "
        f"({len(result)} fields)"
    )
    return result


def deserialize_state(records: dict[str, str], expected_version: int) -> StrategyState:
    """Convert DB records back to StrategyState with type preservation and validation.

    Validates that all required fields are present and have correct types.
    Raises StateValidationError identifying specific invalid fields on failure.

    Args:
        records: Dictionary of {state_key: json_encoded_value} from the DB.
        expected_version: The schema version expected (for validation).

    Returns:
        A validated StrategyState object.

    Raises:
        StateValidationError: When fields are missing, have invalid types,
            or non-nullable fields are None.
    """
    missing_fields: list[str] = []
    invalid_fields: list[str] = []
    parsed_values: dict[str, Any] = {}

    # Check for missing required fields
    for key in REQUIRED_STATE_KEYS:
        if key not in records:
            missing_fields.append(key)

    if missing_fields:
        raise StateValidationError(
            f"Missing required state fields: {', '.join(sorted(missing_fields))}",
            invalid_fields=missing_fields,
        )

    # Parse and validate each field
    for field_name, (expected_type, nullable) in _FIELD_SPECS.items():
        raw_value = records[field_name]

        # Parse JSON string
        try:
            value = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError) as e:
            invalid_fields.append(field_name)
            logger.warning(
                f"StateSerializer: Field '{field_name}' has invalid JSON: {e}"
            )
            continue

        # Check nullability
        if value is None:
            if not nullable:
                invalid_fields.append(field_name)
                logger.warning(
                    f"StateSerializer: Non-nullable field '{field_name}' is None"
                )
                continue
            parsed_values[field_name] = None
            continue

        # Type coercion and validation
        try:
            coerced = _coerce_type(field_name, value, expected_type)
            parsed_values[field_name] = coerced
        except (TypeError, ValueError) as e:
            invalid_fields.append(field_name)
            logger.warning(
                f"StateSerializer: Field '{field_name}' type validation failed: {e}"
            )

    if invalid_fields:
        raise StateValidationError(
            f"Invalid state fields: {', '.join(sorted(invalid_fields))}",
            invalid_fields=invalid_fields,
        )

    # Validate schema version matches expected
    schema_version = parsed_values.get("schema_version")
    if schema_version != expected_version:
        raise StateValidationError(
            f"Schema version mismatch: expected {expected_version}, got {schema_version}",
            invalid_fields=["schema_version"],
        )

    # Construct the StrategyState
    state = StrategyState(**parsed_values)

    logger.debug(
        f"StateSerializer: Deserialized state for strategy '{state.strategy_id}' "
        f"(schema v{state.schema_version})"
    )
    return state


def _coerce_type(field_name: str, value: Any, expected_type: type) -> Any:
    """Coerce a parsed JSON value to the expected Python type.

    Preserves type boundaries:
    - int stays int (not float)
    - bool stays bool (not int)
    - float stays float
    - str stays str
    - dict stays dict
    """
    if expected_type == bool:
        # JSON booleans are already Python bools, but check explicitly
        if not isinstance(value, bool):
            raise TypeError(
                f"Expected bool for '{field_name}', got {type(value).__name__}: {value}"
            )
        return value

    if expected_type == int:
        # Must be an int, not a bool (since bool is a subclass of int in Python)
        if isinstance(value, bool):
            raise TypeError(
                f"Expected int for '{field_name}', got bool: {value}"
            )
        if not isinstance(value, int):
            raise TypeError(
                f"Expected int for '{field_name}', got {type(value).__name__}: {value}"
            )
        return value

    if expected_type == float:
        # Accept int or float from JSON (JSON doesn't distinguish)
        if isinstance(value, bool):
            raise TypeError(
                f"Expected float for '{field_name}', got bool: {value}"
            )
        if isinstance(value, (int, float)):
            return float(value)
        raise TypeError(
            f"Expected float for '{field_name}', got {type(value).__name__}: {value}"
        )

    if expected_type == str:
        if not isinstance(value, str):
            raise TypeError(
                f"Expected str for '{field_name}', got {type(value).__name__}: {value}"
            )
        return value

    if expected_type == dict:
        if not isinstance(value, dict):
            raise TypeError(
                f"Expected dict for '{field_name}', got {type(value).__name__}: {value}"
            )
        return value

    raise TypeError(f"Unsupported type spec for '{field_name}': {expected_type}")


def migrate_state(
    records: dict[str, str], from_version: int, to_version: int
) -> dict[str, str]:
    """Attempt automated migration of state records between schema versions.

    Applies migration steps sequentially from from_version to to_version.

    Args:
        records: The current state records (key-value dict with JSON-encoded values).
        from_version: The current schema version of the records.
        to_version: The target schema version to migrate to.

    Returns:
        Migrated state records at the target version.

    Raises:
        StateValidationError: If migration fails or versions are invalid.
    """
    if from_version == to_version:
        return records

    if from_version > to_version:
        raise StateValidationError(
            f"Cannot downgrade schema from version {from_version} to {to_version}",
            invalid_fields=["schema_version"],
        )

    if from_version < 1:
        raise StateValidationError(
            f"Invalid source schema version: {from_version}",
            invalid_fields=["schema_version"],
        )

    if to_version > CURRENT_SCHEMA_VERSION:
        raise StateValidationError(
            f"Target schema version {to_version} exceeds current version "
            f"{CURRENT_SCHEMA_VERSION}",
            invalid_fields=["schema_version"],
        )

    migrated = dict(records)
    current_version = from_version

    while current_version < to_version:
        next_version = current_version + 1
        migration_fn = _MIGRATIONS.get((current_version, next_version))

        if migration_fn is None:
            raise StateValidationError(
                f"No migration path from schema version {current_version} "
                f"to {next_version}",
                invalid_fields=["schema_version"],
            )

        try:
            migrated = migration_fn(migrated)
            # Update schema_version in the migrated records
            migrated["schema_version"] = json.dumps(next_version)
            current_version = next_version
            logger.info(
                f"StateSerializer: Migrated state from schema v{current_version - 1} "
                f"to v{current_version}"
            )
        except Exception as e:
            raise StateValidationError(
                f"Migration from schema v{current_version} to v{next_version} "
                f"failed: {e}",
                invalid_fields=["schema_version"],
            )

    return migrated


# Migration functions registry: (from_version, to_version) → migration_fn
# Each migration function takes records dict and returns migrated records dict.
# Add new migrations here as schema evolves.
_MIGRATIONS: dict[tuple[int, int], Any] = {
    # Example for future: (1, 2): _migrate_v1_to_v2,
}
