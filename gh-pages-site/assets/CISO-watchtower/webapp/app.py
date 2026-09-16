import logging
import os
from datetime import datetime, timedelta, timezone

import google.auth
from cachetools import TTLCache
from flask import Flask, jsonify, render_template
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# Demo mode with mock data, bypassing BigQuery. Set USE_MOCK_ITEMS env var to true/1/yes to enable.
USE_MOCK_ITEMS = os.environ.get("USE_MOCK_ITEMS", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GCP_PROJECT = os.environ.get("GCP_PROJECT")
BQ_DATASET = os.environ.get("BQ_DATASET", "cloud_news")
MAX_PER_SOURCE = int(os.environ.get("MAX_PER_SOURCE", "10"))

if USE_MOCK_ITEMS:
    try:
        from mock_data import build_mock_items, build_mock_categories
    except ImportError:
        raise RuntimeError(
            "USE_MOCK_ITEMS is set but mock_data.py is not present in this image — "
            "it is excluded from the production build. "
            "Remove USE_MOCK_ITEMS from the Cloud Run environment variables."
        )

if not USE_MOCK_ITEMS and not GCP_PROJECT:
    raise RuntimeError("GCP_PROJECT environment variable must be set")

_bq = None
# TTL of 30 s: the news processor cycles every 60 s so data is at most ~30 s stale.
# _stale holds the last successful BQ result and is served as a fallback when BQ
# is temporarily unreachable after the cache expires.
_cache: TTLCache = TTLCache(maxsize=4, ttl=30)
_stale: dict = {}


def _require_gcp_project():
    if not GCP_PROJECT:
        raise RuntimeError("GCP_PROJECT is required when USE_MOCK_ITEMS is false")


def _table_names():
    _require_gcp_project()
    items_table = f"{GCP_PROJECT}.{BQ_DATASET}.cloud_news_items"
    sources_table = f"{GCP_PROJECT}.{BQ_DATASET}.cloud_news_uris"
    return items_table, sources_table


def _get_bq():
    global _bq
    _require_gcp_project()
    if _bq is None:
        credentials, _ = google.auth.default()
        credentials._universe_domain = "googleapis.com"
        _bq = bigquery.Client(project=GCP_PROJECT, credentials=credentials)
    return _bq


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/items")
def get_items():
    if USE_MOCK_ITEMS:
        return jsonify(build_mock_items())

    if "items" in _cache:
        return jsonify(_cache["items"])

    items_table, sources_table = _table_names()

    query = f"""
        WITH ranked AS (
            SELECT t1.*, t2.categories,
                   ROW_NUMBER() OVER (
                       PARTITION BY t1.uri_id
                       ORDER BY t1.published DESC, t1.`hash` ASC
                   ) AS rn
            FROM `{items_table}` t1
            JOIN `{sources_table}` t2 ON t1.uri_id = t2.id
            WHERE t1.published <= CURRENT_TIMESTAMP()
        )
        SELECT * EXCEPT(rn)
        FROM ranked
        WHERE rn <= {MAX_PER_SOURCE}
        ORDER BY published DESC, `hash` ASC
        LIMIT 100
    """
    try:
        result = [dict(row) for row in _get_bq().query(query).result()]
        _cache["items"] = result
        _stale["items"] = result
        return jsonify(result)
    except Exception as e:
        log.exception("BigQuery query failed")
        if "items" in _stale:
            log.warning("Serving stale /api/items after BQ error")
            return jsonify(_stale["items"])
        return jsonify({"error": str(e)}), 500


@app.route("/api/categories")
def get_categories():
    if USE_MOCK_ITEMS:
        return jsonify(build_mock_categories(build_mock_items()))

    if "categories" in _cache:
        return jsonify(_cache["categories"])

    _, sources_table = _table_names()

    query = f"""
        SELECT DISTINCT cat
        FROM `{sources_table}`
        CROSS JOIN UNNEST(categories) AS cat
        WHERE cat IS NOT NULL AND TRIM(cat) != ''
        ORDER BY cat
    """
    try:
        rows = _get_bq().query(query).result()
        cats = [row.cat for row in rows]
        # Ensure frontend filter has at least one option, even when source metadata is incomplete
        cats.append("uncategorized")
        _cache["categories"] = cats
        _stale["categories"] = cats
        return jsonify(cats)
    except Exception as e:
        log.exception("BigQuery categories query failed")
        if "categories" in _stale:
            log.warning("Serving stale /api/categories after BQ error")
            return jsonify(_stale["categories"])
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
