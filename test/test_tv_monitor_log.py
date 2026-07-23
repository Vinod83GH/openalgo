# test/test_tv_monitor_log.py
# Property-based test for TV Trade Monitor log timestamp format.
# Feature: tv-signal-trade-monitor, Property 9: Log Timestamp Format

import io
import re
import sys
import contextlib
from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Import the function under test
# ---------------------------------------------------------------------------
sys.path.insert(0, "strategies/scripts")
from tv_trade_monitor import log  # noqa: E402


# ===========================================================================
# Feature: tv-signal-trade-monitor, Property 9: Log Timestamp Format
# ===========================================================================


@given(message=st.text(min_size=0, max_size=200))
@settings(max_examples=100, deadline=None)
def test_log_timestamp_format(message):
    """**Validates: Requirements 9.1**

    For any log message, the output line SHALL begin with a valid ISO-format
    timestamp in IST timezone (+05:30).
    """
    # Capture stdout output from log()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        log(message)

    output_line = buf.getvalue().rstrip("\n")

    # 1. Verify the line starts with an ISO timestamp with IST offset (+05:30)
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30 "
    assert re.match(pattern, output_line), (
        f"Log output does not start with valid IST ISO timestamp: {output_line!r}"
    )

    # 2. Extract the timestamp portion (first space-separated token)
    timestamp_str = output_line.split(" ", 1)[0]

    # 3. Verify it parses as a valid datetime via fromisoformat
    parsed = datetime.fromisoformat(timestamp_str)
    assert parsed is not None, f"Failed to parse timestamp: {timestamp_str!r}"

    # 4. Verify the timezone offset is +05:30
    offset = parsed.utcoffset()
    assert offset is not None, "Parsed timestamp has no timezone info"
    total_seconds = int(offset.total_seconds())
    assert total_seconds == 5 * 3600 + 30 * 60, (
        f"Expected UTC offset +05:30 (19800s), got {total_seconds}s"
    )
