"""Tests for webapp/app.py — routes, caching, and BigQuery query structure."""

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bq_client(items_rows=None, cats_rows=None):
    """Return a mock BigQuery client whose .query() dispatches by SQL content."""
    if items_rows is None:
        items_rows = [
            {
                "hash": "h1",
                "uri_id": 1,
                "title": "Test",
                "link": "http://x.com",
                "summary": "S",
                "published": "2026-05-04T00:00:00+00:00",
                "criticality": 50,
                "image_url": "",
                "categories": [],
            }
        ]
    Cat = type("Cat", (), {})
    default_cat = Cat()
    default_cat.cat = "threat_intel"
    if cats_rows is None:
        cats_rows = [default_cat]

    mock_bq = MagicMock()

    def _side_effect(sql, *args, **kwargs):
        result = MagicMock()
        if "cloud_news_items" in sql:
            result.result.return_value = iter(items_rows)
        else:
            result.result.return_value = iter(cats_rows)
        return result

    mock_bq.query.side_effect = _side_effect
    return mock_bq


def _capture_sql():
    """Return a mock BQ client that captures the SQL it receives."""
    captured = {}
    mock_bq = MagicMock()

    def _side_effect(sql, *args, **kwargs):
        captured["sql"] = sql
        m = MagicMock()
        m.result.return_value = iter([])
        return m

    mock_bq.query.side_effect = _side_effect
    return mock_bq, captured


# ---------------------------------------------------------------------------
# Dashboard index
# ---------------------------------------------------------------------------


class TestIndex:
    def test_returns_200(self, webapp_client):
        assert webapp_client.get("/").status_code == 200

    def test_returns_html_content(self, webapp_client):
        r = webapp_client.get("/")
        assert b"html" in r.data.lower()


# ---------------------------------------------------------------------------
# /api/items — mock mode
# ---------------------------------------------------------------------------


class TestItemsMockMode:
    def test_returns_200(self, webapp_client):
        assert webapp_client.get("/api/items").status_code == 200

    def test_returns_list(self, webapp_client):
        data = json.loads(webapp_client.get("/api/items").data)
        assert isinstance(data, list)

    def test_returns_12_items(self, webapp_client):
        data = json.loads(webapp_client.get("/api/items").data)
        assert len(data) == 12

    def test_items_have_required_fields(self, webapp_client):
        item = json.loads(webapp_client.get("/api/items").data)[0]
        for field in ("title", "link", "summary", "published", "criticality"):
            assert field in item, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# /api/categories — mock mode
# ---------------------------------------------------------------------------


class TestCategoriesMockMode:
    def test_returns_200(self, webapp_client):
        assert webapp_client.get("/api/categories").status_code == 200

    def test_returns_list(self, webapp_client):
        data = json.loads(webapp_client.get("/api/categories").data)
        assert isinstance(data, list)

    def test_returns_known_categories(self, webapp_client):
        cats = json.loads(webapp_client.get("/api/categories").data)
        assert "threat_intel" in cats
        assert "cloud_status" in cats

    def test_not_empty(self, webapp_client):
        cats = json.loads(webapp_client.get("/api/categories").data)
        assert len(cats) > 0


# ---------------------------------------------------------------------------
# BigQuery caching
# ---------------------------------------------------------------------------


class TestBQCaching:
    def test_items_bq_called_only_once_across_repeated_requests(self, webapp_client):
        import app as _app

        mock_bq = _make_bq_client()
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            for _ in range(4):
                webapp_client.get("/api/items")
        assert mock_bq.query.call_count == 1

    def test_categories_bq_called_only_once_across_repeated_requests(
        self, webapp_client
    ):
        import app as _app

        mock_bq = _make_bq_client()
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            for _ in range(4):
                webapp_client.get("/api/categories")
        assert mock_bq.query.call_count == 1

    def test_cache_ttl_is_30_seconds(self):
        import app as _app

        assert _app._cache.ttl == 30

    def test_cache_maxsize_is_4(self):
        import app as _app

        assert _app._cache.maxsize == 4

    def test_items_bq_error_returns_500(self, webapp_client):
        import app as _app

        mock_bq = MagicMock()
        mock_bq.query.side_effect = Exception("BQ unreachable")
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            r = webapp_client.get("/api/items")
        assert r.status_code == 500

    def test_categories_bq_error_returns_500(self, webapp_client):
        import app as _app

        mock_bq = MagicMock()
        mock_bq.query.side_effect = Exception("BQ unreachable")
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            r = webapp_client.get("/api/categories")
        assert r.status_code == 500

    def test_categories_response_includes_uncategorized(self, webapp_client):
        import app as _app

        mock_bq = _make_bq_client()
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            cats = json.loads(webapp_client.get("/api/categories").data)
        assert "uncategorized" in cats


# ---------------------------------------------------------------------------
# BigQuery SQL query structure
# ---------------------------------------------------------------------------


class TestBQQueryStructure:
    def test_items_query_has_limit_100(self, webapp_client):
        import app as _app

        mock_bq, captured = _capture_sql()
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            webapp_client.get("/api/items")
        assert "LIMIT 100" in captured["sql"]

    def test_items_query_uses_max_per_source(self, webapp_client):
        import app as _app

        mock_bq, captured = _capture_sql()
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            webapp_client.get("/api/items")
        assert str(_app.MAX_PER_SOURCE) in captured["sql"]

    def test_items_query_joins_both_tables(self, webapp_client):
        import app as _app

        mock_bq, captured = _capture_sql()
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            webapp_client.get("/api/items")
        assert "cloud_news_items" in captured["sql"]
        assert "cloud_news_uris" in captured["sql"]

    def test_categories_query_uses_sources_table(self, webapp_client):
        import app as _app

        mock_bq, captured = _capture_sql()
        with patch.object(_app, "USE_MOCK_ITEMS", False), patch.object(
            _app, "_get_bq", return_value=mock_bq
        ):
            webapp_client.get("/api/categories")
        assert "cloud_news_uris" in captured["sql"]
