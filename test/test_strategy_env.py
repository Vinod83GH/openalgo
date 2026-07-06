# test/test_strategy_env.py
# Unit tests for utils/strategy_env.py
# Covers validate_env_vars and build_subprocess_env helper functions.

import os
from unittest.mock import patch

import pytest

from utils.strategy_env import build_subprocess_env, validate_env_vars


# ===========================================================================
# Unit tests for validate_env_vars
# ===========================================================================


class TestValidateEnvVars:
    """Unit tests for validate_env_vars."""

    def test_none_returns_valid_empty(self):
        """None input returns (True, None, {})."""
        is_valid, error, sanitized = validate_env_vars(None)
        assert is_valid is True
        assert error is None
        assert sanitized == {}

    def test_valid_dict_with_non_empty_values(self):
        """Valid dict with all non-empty string values passes."""
        env = {"STRATEGY_SYMBOL": "NIFTY", "STRATEGY_LOTS": "2"}
        is_valid, error, sanitized = validate_env_vars(env)
        assert is_valid is True
        assert error is None
        assert sanitized == {"STRATEGY_SYMBOL": "NIFTY", "STRATEGY_LOTS": "2"}

    def test_filters_empty_string_values(self):
        """Entries with empty string values are excluded from sanitized output."""
        env = {"STRATEGY_SYMBOL": "NIFTY", "STRATEGY_LOTS": "", "STRATEGY_PRODUCT": ""}
        is_valid, error, sanitized = validate_env_vars(env)
        assert is_valid is True
        assert error is None
        assert sanitized == {"STRATEGY_SYMBOL": "NIFTY"}

    def test_empty_dict_returns_valid_empty(self):
        """Empty dict is valid and returns empty sanitized dict."""
        is_valid, error, sanitized = validate_env_vars({})
        assert is_valid is True
        assert error is None
        assert sanitized == {}

    def test_non_dict_input_string(self):
        """String input returns validation error."""
        is_valid, error, sanitized = validate_env_vars("not a dict")
        assert is_valid is False
        assert error == "env_vars must be a dictionary"
        assert sanitized == {}

    def test_non_dict_input_list(self):
        """List input returns validation error."""
        is_valid, error, sanitized = validate_env_vars(["a", "b"])
        assert is_valid is False
        assert error == "env_vars must be a dictionary"
        assert sanitized == {}

    def test_non_dict_input_number(self):
        """Numeric input returns validation error."""
        is_valid, error, sanitized = validate_env_vars(42)
        assert is_valid is False
        assert error == "env_vars must be a dictionary"
        assert sanitized == {}

    def test_non_string_key(self):
        """Dict with non-string key returns validation error."""
        is_valid, error, sanitized = validate_env_vars({123: "value"})
        assert is_valid is False
        assert error == "env_vars keys must be strings"
        assert sanitized == {}

    def test_non_string_value(self):
        """Dict with non-string value returns validation error."""
        is_valid, error, sanitized = validate_env_vars({"KEY": 123})
        assert is_valid is False
        assert error == "env_vars values must be strings"
        assert sanitized == {}

    def test_all_empty_values_returns_empty_dict(self):
        """Dict where all values are empty strings returns empty sanitized dict."""
        env = {"A": "", "B": "", "C": ""}
        is_valid, error, sanitized = validate_env_vars(env)
        assert is_valid is True
        assert error is None
        assert sanitized == {}


# ===========================================================================
# Unit tests for build_subprocess_env
# ===========================================================================


class TestBuildSubprocessEnv:
    """Unit tests for build_subprocess_env."""

    def test_empty_strategy_vars_returns_parent_env(self):
        """Empty strategy vars returns a copy of the parent environment."""
        result = build_subprocess_env({})
        # Should contain all parent env vars
        for key, value in os.environ.items():
            assert result[key] == value

    def test_strategy_vars_added_to_env(self):
        """Strategy vars are present in the returned environment."""
        strategy_vars = {"STRATEGY_SYMBOL": "NIFTY", "STRATEGY_LOTS": "3"}
        result = build_subprocess_env(strategy_vars)
        assert result["STRATEGY_SYMBOL"] == "NIFTY"
        assert result["STRATEGY_LOTS"] == "3"

    def test_strategy_overrides_parent(self):
        """Strategy vars override parent env for conflicting keys."""
        # Use a key that definitely exists in os.environ
        existing_key = "PATH"
        strategy_vars = {existing_key: "/custom/path"}
        result = build_subprocess_env(strategy_vars)
        assert result[existing_key] == "/custom/path"

    def test_values_converted_to_strings(self):
        """All values in strategy vars are converted to strings."""
        strategy_vars = {"NUM": "42", "BOOL": "True"}
        result = build_subprocess_env(strategy_vars)
        assert result["NUM"] == "42"
        assert result["BOOL"] == "True"
        assert isinstance(result["NUM"], str)
        assert isinstance(result["BOOL"], str)

    def test_does_not_modify_os_environ(self):
        """build_subprocess_env should not modify the actual os.environ."""
        original_env = os.environ.copy()
        strategy_vars = {"NEW_CUSTOM_VAR_FOR_TEST": "test_value"}
        build_subprocess_env(strategy_vars)
        assert "NEW_CUSTOM_VAR_FOR_TEST" not in os.environ
        assert os.environ == original_env

    @patch.dict(os.environ, {"PARENT_VAR": "parent_val"}, clear=True)
    def test_merge_with_controlled_env(self):
        """With a controlled parent env, verify merge behavior."""
        strategy_vars = {"STRATEGY_VAR": "strat_val"}
        result = build_subprocess_env(strategy_vars)
        assert result["PARENT_VAR"] == "parent_val"
        assert result["STRATEGY_VAR"] == "strat_val"
        assert len(result) == 2
