# test/test_broker_credentials_store.py
# Unit tests for blueprints/broker_credentials_store.py CRUD endpoints.
# Validates: Requirements 5.1, 5.2, 5.4, 5.7, 5.8

import os

import pytest

# Set env vars before importing application modules
os.environ.setdefault("DATABASE_URL", "sqlite:///test_broker_creds_store.db")
os.environ.setdefault("API_KEY_PEPPER", "test_pepper_key_for_unit_tests")

from flask import Flask

from blueprints.broker_credentials_store import broker_credentials_store_bp
from database.broker_credentials_db import (
    Base,
    db_session,
    engine,
    get_credentials,
    save_credentials,
)


@pytest.fixture
def app():
    """Create a Flask application for testing."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.register_blueprint(broker_credentials_store_bp)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def setup_teardown():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    db_session.remove()
    Base.metadata.drop_all(bind=engine)


class TestAuthentication:
    """Test that all endpoints require session['user']."""

    def test_list_without_session_returns_401(self, client):
        resp = client.get("/api/broker-credentials/list")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["message"] == "Not authenticated"

    def test_get_without_session_returns_401(self, client):
        resp = client.get("/api/broker-credentials/dhan")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["message"] == "Not authenticated"

    def test_post_without_session_returns_401(self, client):
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={"api_key": "key", "api_secret": "secret"},
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["message"] == "Not authenticated"

    def test_delete_without_session_returns_401(self, client):
        resp = client.delete("/api/broker-credentials/dhan")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["message"] == "Not authenticated"


class TestListCredentials:
    """Tests for GET /api/broker-credentials/list."""

    def test_list_empty(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.get("/api/broker-credentials/list")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"] == []

    def test_list_returns_all_brokers(self, client):
        # Seed data
        save_credentials("alice", "dhan", "key1", "secret1", "cid1", "http://url1")
        save_credentials("alice", "angel", "key2", "secret2", "cid2", "http://url2")

        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.get("/api/broker-credentials/list")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert len(data["data"]) == 2
        broker_names = {c["broker_name"] for c in data["data"]}
        assert broker_names == {"dhan", "angel"}

    def test_list_masks_secrets(self, client):
        save_credentials("alice", "dhan", "mykey", "my_long_secret_value", "cid", "http://url")

        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.get("/api/broker-credentials/list")
        assert resp.status_code == 200
        data = resp.get_json()
        cred = data["data"][0]
        # Secret should be masked
        assert cred["api_secret"] != "my_long_secret_value"
        assert "*" in cred["api_secret"]


class TestGetBrokerCredentials:
    """Tests for GET /api/broker-credentials/<broker>."""

    def test_get_existing_credentials(self, client):
        save_credentials("alice", "dhan", "mykey", "my_secret_123", "cid", "http://url")

        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.get("/api/broker-credentials/dhan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"]["broker_name"] == "dhan"
        assert data["data"]["api_key"] == "mykey"
        # Secret should be masked
        assert data["data"]["api_secret"] != "my_secret_123"
        assert "*" in data["data"]["api_secret"]

    def test_get_nonexistent_broker_returns_null(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.get("/api/broker-credentials/nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"] is None


class TestSaveBrokerCredentials:
    """Tests for POST /api/broker-credentials/<broker>."""

    def test_save_valid_credentials(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={
                "api_key": "test_key",
                "api_secret": "test_secret",
                "client_id": "cid",
                "redirect_url": "http://localhost/dhan/callback",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"

        # Verify stored in DB
        cred = get_credentials("alice", "dhan")
        assert cred is not None
        assert cred["api_key"] == "test_key"
        assert cred["api_secret"] == "test_secret"

    def test_save_empty_api_key_returns_400(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={"api_key": "", "api_secret": "secret"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "API key is required" in data["message"]

    def test_save_whitespace_api_key_returns_400(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={"api_key": "   ", "api_secret": "secret"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "API key is required" in data["message"]

    def test_save_empty_api_secret_returns_400(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={"api_key": "valid_key", "api_secret": ""},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "API secret is required" in data["message"]

    def test_save_whitespace_api_secret_returns_400(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={"api_key": "valid_key", "api_secret": "  \t  "},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "API secret is required" in data["message"]

    def test_save_missing_api_key_returns_400(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={"api_secret": "secret"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "API key is required" in data["message"]

    def test_save_missing_api_secret_returns_400(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={"api_key": "valid_key"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"
        assert "API secret is required" in data["message"]

    def test_save_updates_existing(self, client):
        save_credentials("alice", "dhan", "old_key", "old_secret", "old_cid", "http://old")

        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={
                "api_key": "new_key",
                "api_secret": "new_secret",
                "client_id": "new_cid",
                "redirect_url": "http://new",
            },
        )
        assert resp.status_code == 200
        cred = get_credentials("alice", "dhan")
        assert cred["api_key"] == "new_key"
        assert cred["api_secret"] == "new_secret"

    def test_save_with_additional_config(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.post(
            "/api/broker-credentials/dhan",
            json={
                "api_key": "key",
                "api_secret": "secret",
                "additional_config": '{"market_key": "mk1"}',
            },
        )
        assert resp.status_code == 200
        cred = get_credentials("alice", "dhan")
        assert cred["additional_config"] == '{"market_key": "mk1"}'


class TestDeleteBrokerCredentials:
    """Tests for DELETE /api/broker-credentials/<broker>."""

    def test_delete_existing(self, client):
        save_credentials("alice", "dhan", "key", "secret", "cid", "http://url")

        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.delete("/api/broker-credentials/dhan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"

        # Verify deleted
        assert get_credentials("alice", "dhan") is None

    def test_delete_nonexistent_returns_success(self, client):
        with client.session_transaction() as sess:
            sess["user"] = "alice"
        resp = client.delete("/api/broker-credentials/nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "No credentials found" in data["message"]
