"""Shared fixtures for the test suite.

Environment variables are set here before any service module is imported,
because both app.py and news_processor.py read env vars at module level.
"""

import os

# Must be set before any import of service modules.
# USE_MOCK_ITEMS=true is intentional: it makes mock_data importable at module load
# time (the import is conditional and runs only once). BQ-path tests then override
# this per-test via patch.object(_app, "USE_MOCK_ITEMS", False).
# If you add a new test that exercises the BQ path, you MUST add that patch —
# otherwise it will silently fall through to mock mode.
os.environ["GCP_PROJECT"] = "test-project"
os.environ["USE_MOCK_ITEMS"] = "true"

import pytest


@pytest.fixture
def webapp_client():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def clear_bq_cache():
    """Clear the BigQuery result cache and stale fallback before and after every test."""
    import app as _app

    _app._cache.clear()
    _app._stale.clear()
    yield
    _app._cache.clear()
    _app._stale.clear()
