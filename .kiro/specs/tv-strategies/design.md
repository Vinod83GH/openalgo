# Design Document

## Overview

This feature replaces the global TV alert trading configuration (stored in the `Settings` table) with a dedicated `TvStrategy` model where each named strategy carries its own trading parameters.

## Architecture

The architecture introduces:

1. A new `TvStrategy` SQLAlchemy model in `database/tv_strategy_db.py`
2. CRUD endpoints in `blueprints/admin.py` following the existing JSON API pattern
3. An endpoint rename from `/api/v1/tv-alert-options` to `/api/v1/tv-alert-triggers`
4. Modified alert processing in `blueprints/tv_alert_options.py` that looks up strategy configuration from the database instead of `get_tv_alert_config()`
5. New React pages `TvStrategies.tsx` (list) and `TvStrategyEdit.tsx` (edit/create)
6. Removal of the deprecated `TvAlertOptions.tsx` page and associated admin settings endpoints

## Components and Interfaces

### 1. Database Layer — `database/tv_strategy_db.py`

New module following the pattern established by `kill_switch_db.py`:

```python
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
```

**Design Decisions:**
- `active_days` stored as a comma-separated string (`"Mon,Tue,Wed,Thu,Fri"`) for simplicity — matches SQLite/PostgreSQL compatibility without needing array types.
- TTLCache with 60s TTL caches strategy lookups by name during alert processing.
- Follows the same engine/session pattern as `kill_switch_db.py` for consistency.

### 2. Service Functions — `database/tv_strategy_db.py`

```python
_strategy_cache = TTLCache(maxsize=128, ttl=60)
_cache_lock = threading.Lock()


def init_db():
    """Create the tv_strategy table if it does not exist."""
    from database.db_init_helper import init_db_with_logging
    init_db_with_logging(Base, engine, "TV Strategy DB", logger)


def invalidate_strategy_cache(name: str) -> None:
    with _cache_lock:
        if name in _strategy_cache:
            del _strategy_cache[name]


def get_strategy_by_name(name: str) -> TvStrategy | None:
    """Look up a strategy by name (cached 60s)."""
    with _cache_lock:
        if name in _strategy_cache:
            return _strategy_cache[name]

    strategy = TvStrategy.query.filter_by(name=name).first()
    if strategy:
        with _cache_lock:
            _strategy_cache[name] = strategy
    return strategy


def get_all_strategies() -> list[TvStrategy]:
    """Return all TvStrategy records."""
    return TvStrategy.query.order_by(TvStrategy.name).all()


def create_strategy(name: str, **fields) -> TvStrategy:
    """Create a new TvStrategy. Raises ValueError on validation failures."""
    _validate_fields(fields)
    strategy = TvStrategy(name=name, **fields)
    db_session.add(strategy)
    db_session.commit()
    return strategy


def update_strategy(strategy: TvStrategy, **fields) -> TvStrategy:
    """Update an existing TvStrategy. Raises ValueError on validation failures."""
    _validate_fields(fields)
    for key, value in fields.items():
        if hasattr(strategy, key):
            setattr(strategy, key, value)
    db_session.commit()
    invalidate_strategy_cache(strategy.name)
    return strategy


def delete_strategy(strategy: TvStrategy) -> None:
    """Delete a TvStrategy record."""
    name = strategy.name
    db_session.delete(strategy)
    db_session.commit()
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
```

### 3. Admin CRUD API — `blueprints/admin.py`

New endpoints added to the existing `admin_bp` blueprint:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/api/tv-strategies` | List all strategies |
| GET | `/admin/api/tv-strategies/<name>` | Get single strategy |
| POST | `/admin/api/tv-strategies` | Create strategy |
| PUT | `/admin/api/tv-strategies/<name>` | Update strategy |
| DELETE | `/admin/api/tv-strategies/<name>` | Delete strategy |

```python
@admin_bp.route("/api/tv-strategies")
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_tv_strategies_list():
    """GET: Return all TvStrategy records as JSON array."""
    strategies = get_all_strategies()
    return jsonify({
        "status": "success",
        "data": [_serialize_strategy(s) for s in strategies],
    })


@admin_bp.route("/api/tv-strategies/<name>")
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_tv_strategy_get(name):
    """GET: Return single TvStrategy by name."""
    strategy = get_strategy_by_name(name)
    if not strategy:
        return jsonify({"status": "error", "message": f"Strategy '{name}' not found"}), 404
    return jsonify({"status": "success", "data": _serialize_strategy(strategy)})


@admin_bp.route("/api/tv-strategies", methods=["POST"])
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_tv_strategy_create():
    """POST: Create a new TvStrategy."""
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"status": "error", "message": "Strategy name is required"}), 400

    if get_strategy_by_name(name):
        return jsonify({"status": "error", "message": f"Strategy '{name}' already exists"}), 409

    fields = _extract_strategy_fields(data)
    try:
        strategy = create_strategy(name, **fields)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "success", "data": _serialize_strategy(strategy)}), 201


@admin_bp.route("/api/tv-strategies/<name>", methods=["PUT"])
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_tv_strategy_update(name):
    """PUT: Update an existing TvStrategy."""
    strategy = get_strategy_by_name(name)
    if not strategy:
        return jsonify({"status": "error", "message": f"Strategy '{name}' not found"}), 404

    data = request.get_json()
    fields = _extract_strategy_fields(data)
    try:
        strategy = update_strategy(strategy, **fields)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "success", "data": _serialize_strategy(strategy)})


@admin_bp.route("/api/tv-strategies/<name>", methods=["DELETE"])
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_tv_strategy_delete(name):
    """DELETE: Remove a TvStrategy."""
    strategy = get_strategy_by_name(name)
    if not strategy:
        return jsonify({"status": "error", "message": f"Strategy '{name}' not found"}), 404

    delete_strategy(strategy)
    return jsonify({"status": "success", "message": f"Strategy '{name}' deleted"})


def _serialize_strategy(s: TvStrategy) -> dict:
    return {
        "name": s.name,
        "active_days": s.active_days.split(",") if s.active_days else [],
        "lot_size": s.lot_size,
        "strike_selection": s.strike_selection,
        "enabled": s.enabled,
        "product": s.product,
        "exchange": s.exchange,
    }


def _extract_strategy_fields(data: dict) -> dict:
    fields = {}
    if "active_days" in data:
        days = data["active_days"]
        if isinstance(days, list):
            fields["active_days"] = ",".join(days)
        else:
            fields["active_days"] = str(days)
    if "lot_size" in data:
        fields["lot_size"] = int(data["lot_size"])
    if "strike_selection" in data:
        fields["strike_selection"] = str(data["strike_selection"]).strip().upper()
    if "enabled" in data:
        fields["enabled"] = bool(data["enabled"])
    if "product" in data:
        fields["product"] = str(data["product"]).strip().upper()
    if "exchange" in data:
        fields["exchange"] = str(data["exchange"]).strip().upper()
    return fields
```

### 4. Endpoint Rename — `restx_api/__init__.py`

Change the namespace registration path:

```python
# Before:
api.add_namespace(tv_alert_options_ns, path="/tv-alert-options")

# After:
api.add_namespace(tv_alert_options_ns, path="/tv-alert-triggers")
```

The old path `/api/v1/tv-alert-options` will naturally return 404 since no namespace is registered at that path.

### 5. Alert Processing Changes — `blueprints/tv_alert_options.py`

The `process_tv_alert` function is modified to:

1. Extract `data["strategy"]` from the webhook payload.
2. Call `get_strategy_by_name(strategy_name)` to fetch the `TvStrategy` record.
3. Return 400 if strategy not found, 200 if disabled or day inactive.
4. Pass `strategy.strike_selection` to `resolve_option_symbol()` instead of hardcoded `"ITM2"`.
5. Use `strategy.lot_size`, `strategy.product`, `strategy.exchange` in `build_order_data()`.

```python
def resolve_option_symbol(
    symbol: str,
    cmp: float,
    option_type: str,
    api_key: str,
    exchange: str,
    strike_offset: str = "ITM2",  # NEW: dynamic offset parameter
) -> tuple:
    """Resolve option symbol using the provided strike offset."""
    expiry = get_nearest_expiry(symbol, exchange)
    if not expiry:
        return False, None, f"No expiry dates found for {symbol} on {exchange}"

    success, response_data, status_code = get_option_symbol(
        underlying=symbol.upper(),
        exchange=exchange.upper(),
        expiry_date=expiry,
        strike_int=None,
        offset=strike_offset,  # Use strategy's strike_selection
        option_type=option_type.upper(),
        api_key=api_key,
        underlying_ltp=cmp,
    )
    # ... rest unchanged


def build_order_data(
    api_key: str,
    resolved_symbol: str,
    signal: str,
    sl: float,
    target: float,
    exchange: str,
    limit_price: float = 0,
    lot_size: int = 1,      # NEW: from strategy
    product: str = "MIS",   # NEW: from strategy
) -> dict:
    """Build order data using strategy-level configuration."""
    order_data = {
        "apikey": api_key,
        "strategy": "TV Alert Options",
        "symbol": resolved_symbol,
        "exchange": exchange,
        "action": signal.upper(),
        "quantity": str(lot_size),    # Use strategy lot_size
        "pricetype": "LIMIT",
        "product": product,           # Use strategy product
        "price": str(limit_price),
        "trigger_price": "0",
        "disclosed_quantity": "0",
        "target": str(target),
        "stoploss": str(sl),
    }
    return order_data
```

**Updated `process_tv_alert` flow:**

```python
def process_tv_alert(data: dict) -> tuple:
    # 1. Authenticate API key (unchanged)
    # 2. Validate payload fields (add "strategy" to REQUIRED_FIELDS)
    # 3. Look up TvStrategy by name
    strategy_name = data.get("strategy", "")
    tv_strategy = get_strategy_by_name(strategy_name)
    if not tv_strategy:
        return {"status": "error", "message": f"Unknown strategy: {strategy_name}"}, 400

    # 4. Check enabled gate
    if not tv_strategy.enabled:
        return {"status": "ignored", "message": f"Strategy '{strategy_name}' is disabled"}, 200

    # 5. Check active_days gate
    today_abbr = datetime.now().strftime("%a")  # "Mon", "Tue", etc.
    active_days_list = tv_strategy.active_days.split(",")
    if today_abbr not in active_days_list:
        return {"status": "ignored", "message": f"Strategy '{strategy_name}' not active on {today_abbr}"}, 200

    # 6. Resolve symbol using strategy's strike_selection
    exchange = tv_strategy.exchange
    if charttype == "SPOT_OPTIONS":
        success, resolved_symbol, error_msg = resolve_option_symbol(
            symbol=symbol, cmp=cmp, option_type=option_type,
            api_key=api_key, exchange=exchange,
            strike_offset=tv_strategy.strike_selection,
        )
        # ...

    # 7. Build order with strategy's lot_size, product, exchange
    order_data = build_order_data(
        api_key=api_key, resolved_symbol=resolved_symbol,
        signal=signal, sl=sl, target=target,
        exchange=exchange, limit_price=limit_price,
        lot_size=tv_strategy.lot_size,
        product=tv_strategy.product,
    )
    # ... place order, log, emit event
```

### 6. Frontend — React Pages

#### `frontend/src/pages/admin/TvStrategies.tsx` (List Page)

- Route: `/admin/tv-strategies`
- Fetches `GET /admin/api/tv-strategies`
- Displays a table with columns: Name, Enabled, Active Days, Lot Size, Product, Exchange
- Each row links to `/admin/tv-strategies/{name}`
- "New Strategy" button navigates to `/admin/tv-strategies/new`
- Delete button per row with confirmation dialog

#### `frontend/src/pages/admin/TvStrategyEdit.tsx` (Edit/Create Page)

- Route: `/admin/tv-strategies/:strategyName`
- If `strategyName === "new"`, renders a blank form for creation (POST)
- Otherwise fetches `GET /admin/api/tv-strategies/{name}` and pre-fills the form (PUT on save)
- Fields:
  - **Name**: text input
  - **Active Days**: 5 checkboxes (Mon–Fri)
  - **Lot Size**: numeric input (min=1)
  - **Strike Selection**: dropdown (ITM5 through OTM5)
  - **Enabled**: toggle switch
  - **Product**: dropdown (MIS/NRML)
  - **Exchange**: dropdown (NFO/BFO/MCX/CDS)
- Client-side validation: lot_size >= 1
- Displays API error messages in a toast without clearing form state

#### Router Changes in `App.tsx`

```tsx
// Remove:
const TvAlertOptions = lazy(() => import('@/pages/admin/TvAlertOptions'))
// <Route path="/admin/tv-alert-options" element={<TvAlertOptions />} />

// Add:
const TvStrategies = lazy(() => import('@/pages/admin/TvStrategies'))
const TvStrategyEdit = lazy(() => import('@/pages/admin/TvStrategyEdit'))
// <Route path="/admin/tv-strategies" element={<TvStrategies />} />
// <Route path="/admin/tv-strategies/:strategyName" element={<TvStrategyEdit />} />
```

### 7. Deprecation Removals

- Delete `frontend/src/pages/admin/TvAlertOptions.tsx`
- Remove export from `frontend/src/pages/admin/index.ts`
- Remove `api_tv_alert_settings_get` and `api_tv_alert_settings_update` from `blueprints/admin.py`
- Remove import of `get_tv_alert_config` / `set_tv_alert_config` from `blueprints/admin.py`
- Remove `get_tv_alert_config()` calls from `blueprints/tv_alert_options.py`

## Data Models

### TvStrategy Table Schema

| Column | Type | Constraints | Default |
|--------|------|-------------|---------|
| id | Integer | Primary key, auto-increment | — |
| name | String(100) | Unique, not null, indexed | — |
| active_days | String(50) | Not null | `"Mon,Tue,Wed,Thu,Fri"` |
| lot_size | Integer | Not null, check >= 1 | `1` |
| strike_selection | String(10) | Not null | `"ITM2"` |
| enabled | Boolean | Not null | `True` |
| product | String(10) | Not null | `"MIS"` |
| exchange | String(10) | Not null | `"NFO"` |

### JSON Serialization Format

```json
{
  "name": "nifty-scalp",
  "active_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "lot_size": 2,
  "strike_selection": "ITM2",
  "enabled": true,
  "product": "MIS",
  "exchange": "NFO"
}
```

### Webhook Payload (Updated)

```json
{
  "apikey": "...",
  "strategy": "nifty-scalp",
  "cmp": 24500.50,
  "symbol": "NIFTY",
  "charttype": "SPOT_OPTIONS",
  "signal": "BUY",
  "option_type": "CE",
  "sl": 20,
  "target": 40
}
```

## Interfaces

### Admin API Request/Response Examples

**POST `/admin/api/tv-strategies`**
```json
// Request
{
  "name": "nifty-scalp",
  "lot_size": 2,
  "strike_selection": "ITM2",
  "product": "MIS",
  "exchange": "NFO",
  "active_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "enabled": true
}

// Response 201
{
  "status": "success",
  "data": { ... }
}

// Response 409 (duplicate name)
{
  "status": "error",
  "message": "Strategy 'nifty-scalp' already exists"
}
```

**PUT `/admin/api/tv-strategies/nifty-scalp`**
```json
// Request (partial updates allowed)
{
  "lot_size": 3,
  "enabled": false
}

// Response 200
{
  "status": "success",
  "data": { ... }
}
```

## Error Handling

| Scenario | HTTP Code | Response Message |
|----------|-----------|-----------------|
| Strategy name not found (GET/PUT/DELETE) | 404 | `"Strategy '{name}' not found"` |
| Duplicate strategy name (POST) | 409 | `"Strategy '{name}' already exists"` |
| Invalid lot_size (< 1) | 400 | `"lot_size must be at least 1"` |
| Invalid exchange | 400 | `"exchange must be one of: BFO, CDS, MCX, NFO"` |
| Invalid product | 400 | `"product must be one of: MIS, NRML"` |
| Invalid strike_selection | 400 | `"strike_selection must be one of: ITM5, ITM4, ..."` |
| Unknown strategy in webhook | 400 | `"Unknown strategy: {name}"` |
| Strategy disabled | 200 | `"Strategy '{name}' is disabled"` |
| Day not active | 200 | `"Strategy '{name}' not active on {day}"` |
| Old endpoint hit | 404 | Flask default 404 |

## Testing Strategy

**Unit Tests (example-based):**
- Endpoint rename: verify `/api/v1/tv-alert-triggers` responds and `/api/v1/tv-alert-options` returns 404
- Frontend route removal: old `/admin/tv-alert-options` page no longer accessible
- Admin settings deprecation: `/admin/api/tv-alert-settings` endpoints return 404
- UI rendering: list page and edit page render correct form elements

**Property Tests (randomized):**
- Strategy CRUD round-trip (create → read → verify fields match)
- Validation rejection (invalid lot_size, exchange, product, strike_selection)
- Strategy lookup during alert processing (config values flow into order data)
- Enabled/disabled and active_days gating behavior

**Integration Tests:**
- Full webhook flow with a real TvStrategy record: create strategy, fire webhook, verify order uses strategy config

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Strategy persistence round-trip

*For any* valid TvStrategy record (with name, active_days from Mon–Fri, lot_size >= 1, strike_selection in ITM5..OTM5, product in MIS/NRML, exchange in NFO/BFO/MCX/CDS), creating it and then reading it back by name should return a record with all fields identical to what was submitted.

**Validates: Requirements 1.1, 2.2, 2.3**

### Property 2: Name uniqueness enforcement

*For any* strategy name, after successfully creating a strategy with that name, attempting to create a second strategy with the same name should fail with HTTP 409 and the original record should remain unchanged.

**Validates: Requirements 1.2, 2.6**

### Property 3: Default field values on creation

*For any* strategy created with only a name provided (no active_days, no enabled field specified), the resulting record should have enabled=true and active_days containing all five weekdays (Mon through Fri).

**Validates: Requirements 1.3, 1.4**

### Property 4: Lot size validation rejects non-positive values

*For any* integer value less than 1, attempting to create or update a strategy with that lot_size should be rejected with HTTP 400, and the database state should remain unchanged.

**Validates: Requirements 1.5, 2.8**

### Property 5: Invalid enum values rejected

*For any* string not in the valid set for exchange (not in {NFO, BFO, MCX, CDS}), product (not in {MIS, NRML}), or strike_selection (not in ITM5..OTM5), a POST or PUT request containing that value should return HTTP 400 with a descriptive error, and no database mutation should occur.

**Validates: Requirements 2.9, 2.10, 2.11**

### Property 6: Non-existent strategy returns 404

*For any* strategy name that has not been created in the database, GET, PUT, and DELETE requests referencing that name should all return HTTP 404.

**Validates: Requirements 2.7**

### Property 7: Delete removes strategy

*For any* existing strategy, after a successful DELETE request, a subsequent GET request for that name should return HTTP 404, and the list endpoint should not include that strategy.

**Validates: Requirements 2.5**

### Property 8: Unknown strategy in webhook returns 400

*For any* webhook payload where the "strategy" field value does not match any TvStrategy record name in the database, the trigger endpoint should return HTTP 400 with a message containing "Unknown strategy: {name}".

**Validates: Requirements 4.2**

### Property 9: Disabled strategy rejects alerts gracefully

*For any* TvStrategy with enabled=false, when a webhook payload references that strategy name, the trigger endpoint should return HTTP 200 with a message indicating the strategy is disabled, and no order should be placed.

**Validates: Requirements 4.3**

### Property 10: Inactive day rejects alerts gracefully

*For any* TvStrategy where the current weekday is not in the active_days set, when a webhook payload references that strategy name, the trigger endpoint should return HTTP 200 with a message indicating the day is not active, and no order should be placed.

**Validates: Requirements 4.5**

### Property 11: Strategy configuration flows into order data

*For any* enabled TvStrategy with today in active_days, when a webhook is processed for that strategy, the resulting order should use lot_size as quantity, product as the order product type, and exchange as the order exchange — matching the strategy record exactly.

**Validates: Requirements 4.6, 4.8, 4.9**

### Property 12: Strike selection flows into option symbol resolution

*For any* enabled TvStrategy with a SPOT_OPTIONS webhook, the strike offset passed to the option symbol resolution function should equal the strategy's strike_selection value (not the old hardcoded "ITM2").

**Validates: Requirements 4.7**
