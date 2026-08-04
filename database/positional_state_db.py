# database/positional_state_db.py
"""
Positional State Database Module
Handles per-strategy state persistence for positional (multi-day) trading strategies.

Each strategy gets its own table: positional_state_{strategy_id}
State is stored as key-value pairs with schema versioning for migration support.
"""

import os
import time
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Table,
    MetaData,
    create_engine,
    inspect,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

from utils.logging import get_logger

logger = get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Follow the same engine pattern as other database modules
if DATABASE_URL and "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL, poolclass=NullPool, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL, pool_size=50, max_overflow=100, pool_timeout=10)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

# Metadata for dynamic table operations
metadata = MetaData()

# Retry configuration
MAX_RETRIES = 3
RETRY_INTERVAL_SECONDS = 2

# Table name prefix
TABLE_PREFIX = "positional_state_"


def _get_table_name(strategy_id: str) -> str:
    """Get the table name for a given strategy_id."""
    return f"{TABLE_PREFIX}{strategy_id}"


def _get_table(strategy_id: str) -> Table:
    """Get or create a SQLAlchemy Table object for the given strategy_id."""
    table_name = _get_table_name(strategy_id)

    # Check if table is already in metadata
    if table_name in metadata.tables:
        return metadata.tables[table_name]

    # Define the table dynamically
    table = Table(
        table_name,
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("state_key", String(255), unique=True, nullable=False),
        Column("state_value", Text(65535), nullable=False),
        Column("schema_version", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False, default=datetime.now(timezone.utc)),
        Column("updated_at", DateTime, nullable=False, default=datetime.now(timezone.utc)),
        extend_existing=True,
    )
    return table


def create_strategy_table(strategy_id: str) -> bool:
    """Create a dedicated state table for a strategy.

    Table name: positional_state_{strategy_id}

    Args:
        strategy_id: Unique identifier for the strategy.

    Returns:
        True if table was created or already exists, False on failure.
    """
    try:
        table = _get_table(strategy_id)
        table.create(engine, checkfirst=True)
        logger.info(f"Positional State DB: Table created for strategy '{strategy_id}'")
        return True
    except Exception as e:
        logger.error(
            f"Positional State DB: Failed to create table for strategy '{strategy_id}': {e}"
        )
        return False


def save_state(strategy_id: str, state: dict, schema_version: int) -> bool:
    """Persist strategy state to the database with atomic write.

    Performs delete-all + insert-all in a single transaction.
    Retries up to 3 times with 2-second intervals on failure.

    Args:
        strategy_id: Unique identifier for the strategy.
        state: Dictionary of {state_key: state_value} pairs to persist.
        schema_version: Version number for schema migration support.

    Returns:
        True if state was saved successfully, False if all retries failed.
    """
    table = _get_table(strategy_id)
    now = datetime.now(timezone.utc)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            connection = engine.connect()
            transaction = connection.begin()
            try:
                # Delete all existing rows (atomic: delete-all + insert-all)
                connection.execute(table.delete())

                # Insert all state key-value pairs
                rows = [
                    {
                        "state_key": key,
                        "state_value": value,
                        "schema_version": schema_version,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for key, value in state.items()
                ]

                if rows:
                    connection.execute(table.insert(), rows)

                transaction.commit()
                logger.info(
                    f"Positional State DB: State saved for strategy '{strategy_id}' "
                    f"({len(state)} keys, schema v{schema_version})"
                )
                return True
            except Exception:
                transaction.rollback()
                raise
            finally:
                connection.close()
        except Exception as e:
            logger.warning(
                f"Positional State DB: Write attempt {attempt}/{MAX_RETRIES} failed "
                f"for strategy '{strategy_id}': {e}"
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_INTERVAL_SECONDS)

    logger.error(
        f"Positional State DB: All {MAX_RETRIES} write attempts failed "
        f"for strategy '{strategy_id}'"
    )
    return False


def load_state(strategy_id: str) -> dict | None:
    """Load strategy state from the database.

    Args:
        strategy_id: Unique identifier for the strategy.

    Returns:
        Dictionary of {state_key: state_value} if state exists, None otherwise.
    """
    table_name = _get_table_name(strategy_id)

    try:
        # Check if the table exists first
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            logger.debug(
                f"Positional State DB: No table found for strategy '{strategy_id}'"
            )
            return None

        table = _get_table(strategy_id)
        connection = engine.connect()
        try:
            result = connection.execute(table.select())
            rows = result.fetchall()

            if not rows:
                return None

            state = {}
            for row in rows:
                state[row.state_key] = row.state_value

            logger.info(
                f"Positional State DB: State loaded for strategy '{strategy_id}' "
                f"({len(state)} keys)"
            )
            return state
        finally:
            connection.close()
    except Exception as e:
        logger.error(
            f"Positional State DB: Failed to load state for strategy '{strategy_id}': {e}"
        )
        return None


def delete_strategy_table(strategy_id: str) -> bool:
    """Delete the state table for a strategy (cleanup).

    Args:
        strategy_id: Unique identifier for the strategy.

    Returns:
        True if table was deleted or didn't exist, False on failure.
    """
    table_name = _get_table_name(strategy_id)

    try:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            logger.debug(
                f"Positional State DB: Table for strategy '{strategy_id}' "
                f"does not exist, nothing to delete"
            )
            return True

        table = _get_table(strategy_id)
        table.drop(engine)

        # Remove from metadata cache
        if table_name in metadata.tables:
            metadata.remove(table)

        logger.info(
            f"Positional State DB: Table deleted for strategy '{strategy_id}'"
        )
        return True
    except Exception as e:
        logger.error(
            f"Positional State DB: Failed to delete table for strategy '{strategy_id}': {e}"
        )
        return False


def get_all_strategies_with_state() -> list[str]:
    """Get a list of all strategy_ids that have persisted state tables.

    Returns:
        List of strategy_id strings that have positional_state_ tables in the database.
    """
    try:
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()

        strategy_ids = []
        for table_name in all_tables:
            if table_name.startswith(TABLE_PREFIX):
                strategy_id = table_name[len(TABLE_PREFIX):]
                if strategy_id:
                    strategy_ids.append(strategy_id)

        logger.debug(
            f"Positional State DB: Found {len(strategy_ids)} strategies with persisted state"
        )
        return strategy_ids
    except Exception as e:
        logger.error(
            f"Positional State DB: Failed to list strategies with state: {e}"
        )
        return []
