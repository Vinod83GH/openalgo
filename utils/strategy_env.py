"""
Utility functions for per-strategy environment variable validation and merging.

These helpers support the Strategy Parameters feature, which allows traders to configure
per-strategy environment variables (STRATEGY_SYMBOL, STRATEGY_LOTS, etc.) that are
injected into the subprocess at launch time.
"""

import os


def validate_env_vars(env_vars):
    """
    Validate and sanitize environment variables from request data.

    Args:
        env_vars: Raw env_vars data from request (could be any type)

    Returns:
        tuple: (is_valid, error_message, sanitized_dict)
            - is_valid: True if validation passed
            - error_message: Human-readable error if invalid, None otherwise
            - sanitized_dict: Filtered dict with only non-empty string values
    """
    # None or missing → valid with empty dict
    if env_vars is None:
        return (True, None, {})

    # Must be a dict
    if not isinstance(env_vars, dict):
        return (False, "env_vars must be a dictionary", {})

    # Validate all keys and values are strings
    for key, value in env_vars.items():
        if not isinstance(key, str):
            return (False, "env_vars keys must be strings", {})
        if not isinstance(value, str):
            return (False, "env_vars values must be strings", {})

    # Filter out entries where value is empty string
    sanitized = {k: v for k, v in env_vars.items() if v != ""}

    return (True, None, sanitized)


def build_subprocess_env(strategy_env_vars):
    """
    Build the environment dictionary for a strategy subprocess.

    Merges the current process environment with strategy-specific env vars.
    Strategy values override parent values for conflicting keys.
    All values are converted to strings.

    Args:
        strategy_env_vars: Dict of strategy-specific environment variables

    Returns:
        dict: Complete environment dict for subprocess.Popen(env=...)
    """
    env = os.environ.copy()
    for key, value in strategy_env_vars.items():
        env[key] = str(value)
    return env
