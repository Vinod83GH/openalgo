# test/test_broker_credentials_db.py
# Unit tests for database/broker_credentials_db.py CRUD helpers.
# Validates: Requirements 5.2, 5.3, 5.5, 5.6, 5.7

import os

import pytest

# Set env vars before importing the module
os.environ.setdefault("DATABASE_URL", "sqlite:///test_broker_creds.db")
os.environ.setdefault("API_KEY_PEPPER", "test_pepper_key_for_unit_tests")

from database.broker_credentials_db import (
    Base,
    db_session,
    delete_credentials,
    engine,
    get_all_credentials,
    get_credentials,
    mask_secret,
    save_credentials,
)


@pytest.fixture(autouse=True)
def setup_teardown():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    db_session.remove()
    Base.metadata.drop_all(bind=engine)


class TestMaskSecret:
    """Tests for the mask_secret helper."""

    def test_mask_normal_string(self):
        result = mask_secret("my_secret_key")
        assert result == "my_s*********"

    def test_mask_with_custom_show_chars(self):
        result = mask_secret("abcdefgh", show_chars=2)
        assert result == "ab******"

    def test_mask_none_returns_empty(self):
        assert mask_secret(None) == ""

    def test_mask_empty_string_returns_empty(self):
        assert mask_secret("") == ""

    def test_mask_short_string_returns_as_is(self):
        # String shorter than or equal to show_chars
        assert mask_secret("abc", show_chars=4) == "abc"
        assert mask_secret("abcd", show_chars=4) == "abcd"

    def test_mask_exactly_one_more_than_show_chars(self):
        result = mask_secret("abcde", show_chars=4)
        assert result == "abcd*"


class TestSaveCredentials:
    """Tests for save_credentials (insert and update)."""

    def test_save_new_credentials(self):
        result = save_credentials(
            username="alice",
            broker_name="dhan",
            api_key="key123",
            api_secret="secret456",
            client_id="client789",
            redirect_url="http://localhost/callback",
        )
        assert result is True

    def test_save_updates_existing(self):
        # First save
        save_credentials("bob", "angel", "key1", "secret1", "c1", "http://url1")

        # Second save (upsert)
        save_credentials("bob", "angel", "key2", "secret2", "c2", "http://url2")

        # Retrieve and verify updated values
        cred = get_credentials("bob", "angel")
        assert cred["api_key"] == "key2"
        assert cred["api_secret"] == "secret2"
        assert cred["client_id"] == "c2"
        assert cred["redirect_url"] == "http://url2"

    def test_save_with_additional_config(self):
        save_credentials(
            "alice", "dhan", "key", "secret", "cid", "http://url",
            additional_config='{"market_api_key": "mkt123"}'
        )
        cred = get_credentials("alice", "dhan")
        assert cred["additional_config"] == '{"market_api_key": "mkt123"}'

    def test_save_with_none_additional_config(self):
        save_credentials("alice", "dhan", "key", "secret", "cid", "http://url")
        cred = get_credentials("alice", "dhan")
        assert cred["additional_config"] is None


class TestGetCredentials:
    """Tests for get_credentials."""

    def test_get_existing_credentials(self):
        save_credentials("carol", "zerodha", "zkey", "zsecret", "zclient", "http://zurl")
        cred = get_credentials("carol", "zerodha")
        assert cred is not None
        assert cred["broker_name"] == "zerodha"
        assert cred["api_key"] == "zkey"
        assert cred["api_secret"] == "zsecret"  # Decrypted
        assert cred["client_id"] == "zclient"
        assert cred["redirect_url"] == "http://zurl"

    def test_get_nonexistent_returns_none(self):
        cred = get_credentials("nobody", "unknown_broker")
        assert cred is None

    def test_get_decrypts_secret(self):
        """Verify that stored encrypted secret is decrypted on retrieval."""
        save_credentials("dave", "angel", "k", "my_super_secret", "c", "http://u")
        cred = get_credentials("dave", "angel")
        assert cred["api_secret"] == "my_super_secret"


class TestGetAllCredentials:
    """Tests for get_all_credentials."""

    def test_get_all_multiple_brokers(self):
        save_credentials("eve", "dhan", "k1", "s1", "c1", "http://u1")
        save_credentials("eve", "angel", "k2", "s2", "c2", "http://u2")
        save_credentials("eve", "zerodha", "k3", "s3", "c3", "http://u3")

        all_creds = get_all_credentials("eve")
        assert len(all_creds) == 3
        broker_names = {c["broker_name"] for c in all_creds}
        assert broker_names == {"dhan", "angel", "zerodha"}

    def test_get_all_masks_secrets(self):
        save_credentials("frank", "dhan", "key", "long_secret_value", "cid", "http://url")
        all_creds = get_all_credentials("frank")
        assert len(all_creds) == 1
        # Secret should be masked, not the full plaintext
        assert all_creds[0]["api_secret"] != "long_secret_value"
        assert all_creds[0]["api_secret"].startswith("long")
        assert "*" in all_creds[0]["api_secret"]

    def test_get_all_empty_user(self):
        result = get_all_credentials("ghost_user")
        assert result == []


class TestDeleteCredentials:
    """Tests for delete_credentials."""

    def test_delete_existing(self):
        save_credentials("grace", "dhan", "k", "s", "c", "http://u")
        result = delete_credentials("grace", "dhan")
        assert result is True
        # Verify deleted
        assert get_credentials("grace", "dhan") is None

    def test_delete_nonexistent_returns_false(self):
        result = delete_credentials("nobody", "fake_broker")
        assert result is False

    def test_delete_does_not_affect_other_brokers(self):
        save_credentials("heidi", "dhan", "k1", "s1", "c1", "http://u1")
        save_credentials("heidi", "angel", "k2", "s2", "c2", "http://u2")

        delete_credentials("heidi", "dhan")
        # Angel should still exist
        assert get_credentials("heidi", "angel") is not None
        assert get_credentials("heidi", "dhan") is None
