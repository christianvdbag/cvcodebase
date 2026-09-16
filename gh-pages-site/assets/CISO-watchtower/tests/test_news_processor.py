"""Tests for news_processor/news_processor.py — article parsing, deduplication, BQ helpers."""

import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import news_processor as np_mod
from news_processor import (
    extract_articles,
    parse_article,
    save_articles,
    update_fetch_timestamps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_entry(
    title="Test Article", link="http://example.com/1", days_old=0, guid=None
):
    """Build a minimal feedparser entry dict with a recent timestamp."""
    now = datetime.now(timezone.utc) - timedelta(days=days_old)
    return {
        "title": title,
        "link": link,
        "summary": "Test summary",
        "id": guid if guid is not None else link,
        "published_parsed": (
            now.year,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second,
        ),
    }


def make_feed_info(entries, feed_id=1, criticality=50):
    return {
        "id": feed_id,
        "vendor": "TestVendor",
        "criticality": criticality,
        "data": {"entries": entries},
    }


@pytest.fixture
def session():
    return MagicMock()


@pytest.fixture
def sem():
    return asyncio.Semaphore(1)


@pytest.fixture
def cutoff():
    """A cutoff 7 days in the past (same as the real processor uses)."""
    return datetime.now(timezone.utc) - timedelta(weeks=1)


# ---------------------------------------------------------------------------
# parse_article
# ---------------------------------------------------------------------------


class TestParseArticle:
    async def test_returns_dict_for_valid_entry(self, session, sem, cutoff):
        with patch(
            "news_processor.get_item_image_url",
            new=AsyncMock(return_value="http://img.png"),
        ):
            result = await parse_article(
                make_entry(),
                feed_id=1,
                criticality=50,
                cutoff=cutoff,
                session=session,
                sem=sem,
            )
        assert isinstance(result, dict)

    async def test_hash_is_md5_of_feed_id_and_guid(self, session, sem, cutoff):
        entry = make_entry(guid="guid-abc")
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            result = await parse_article(
                entry,
                feed_id=7,
                criticality=50,
                cutoff=cutoff,
                session=session,
                sem=sem,
            )
        expected = hashlib.md5(b"7guid-abc").hexdigest()
        assert result["hash"] == expected

    async def test_old_article_returns_none(self, session, sem):
        future_cutoff = datetime.now(timezone.utc) + timedelta(days=1)
        entry = make_entry(days_old=2)
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            result = await parse_article(
                entry,
                feed_id=1,
                criticality=50,
                cutoff=future_cutoff,
                session=session,
                sem=sem,
            )
        assert result is None

    async def test_uses_link_as_fallback_guid_when_id_missing(
        self, session, sem, cutoff
    ):
        entry = {
            "title": "T",
            "link": "http://fallback.com/1",
            "summary": "S",
            "published_parsed": make_entry()["published_parsed"],
        }
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            result = await parse_article(
                entry,
                feed_id=3,
                criticality=50,
                cutoff=cutoff,
                session=session,
                sem=sem,
            )
        expected = hashlib.md5(b"3http://fallback.com/1").hexdigest()
        assert result["hash"] == expected

    async def test_criticality_is_preserved(self, session, sem, cutoff):
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            result = await parse_article(
                make_entry(),
                feed_id=1,
                criticality=80,
                cutoff=cutoff,
                session=session,
                sem=sem,
            )
        assert result["criticality"] == 80

    async def test_all_required_fields_present(self, session, sem, cutoff):
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            result = await parse_article(
                make_entry(),
                feed_id=1,
                criticality=50,
                cutoff=cutoff,
                session=session,
                sem=sem,
            )
        for field in (
            "hash",
            "uri_id",
            "title",
            "link",
            "summary",
            "published",
            "criticality",
            "image_url",
        ):
            assert field in result, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# extract_articles
# ---------------------------------------------------------------------------


class TestExtractArticles:
    async def test_skips_article_with_existing_hash(self, session):
        entry = make_entry(guid="dup-1")
        existing_hash = hashlib.md5(b"1dup-1").hexdigest()
        feed_info = make_feed_info([entry])
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            result = await extract_articles(
                feed_info, {existing_hash}, session, asyncio.Semaphore(1)
            )
        assert result == []

    async def test_returns_new_articles_only(self, session):
        entries = [make_entry(guid="new-1"), make_entry(guid="new-2")]
        feed_info = make_feed_info(entries)
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            result = await extract_articles(
                feed_info, set(), session, asyncio.Semaphore(5)
            )
        assert len(result) == 2

    async def test_empty_feed_returns_empty_list(self, session):
        result = await extract_articles(
            make_feed_info([]), set(), session, asyncio.Semaphore(1)
        )
        assert result == []

    async def test_new_hashes_added_to_existing_set(self, session):
        entry = make_entry(guid="track-1")
        existing = set()
        with patch(
            "news_processor.get_item_image_url", new=AsyncMock(return_value=None)
        ):
            await extract_articles(
                make_feed_info([entry]), existing, session, asyncio.Semaphore(1)
            )
        assert len(existing) == 1


# ---------------------------------------------------------------------------
# save_articles / update_fetch_timestamps — BQ write helpers
# ---------------------------------------------------------------------------


class TestSaveArticles:
    def test_empty_list_does_not_call_bq(self):
        with patch.object(np_mod, "_get_bq") as mock_get_bq:
            save_articles([])
        mock_get_bq.assert_not_called()

    def test_non_empty_list_calls_insert_rows_json(self):
        mock_bq = MagicMock()
        mock_bq.insert_rows_json.return_value = []
        with patch.object(np_mod, "_get_bq", return_value=mock_bq):
            save_articles([{"hash": "h1", "title": "T"}])
        mock_bq.insert_rows_json.assert_called_once()


class TestUpdateFetchTimestamps:
    def test_empty_list_does_not_call_bq(self):
        with patch.object(np_mod, "_get_bq") as mock_get_bq:
            update_fetch_timestamps([])
        mock_get_bq.assert_not_called()

    def test_non_empty_list_runs_merge_query(self):
        mock_bq = MagicMock()
        mock_bq.query.return_value.result.return_value = None
        with patch.object(np_mod, "_get_bq", return_value=mock_bq):
            update_fetch_timestamps([1, 2, 3])
        mock_bq.query.assert_called_once()
        sql = mock_bq.query.call_args[0][0]
        assert "MERGE" in sql
