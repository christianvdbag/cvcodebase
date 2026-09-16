import asyncio
import hashlib
import logging
import os
import ssl
import sys
import time
from datetime import datetime, timezone, timedelta

import aiohttp
import feedparser
from aiohttp import web
import google.auth
from google.cloud import bigquery

from image_utils import get_item_image_url

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

GCP_PROJECT = os.environ["GCP_PROJECT"]
BQ_DATASET = os.environ.get("BQ_DATASET", "cloud_news")
SOURCES_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.cloud_news_uris"
ITEMS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.cloud_news_items"

SSL_CTX = ssl.create_default_context()

# Our environment uses Zscaler HTTPS inspection, which re-signs upstream certs
# with a Zscaler CA that this container does not currently trust.
# When HTTPS_PROXY is set, cert/hostname validation is disabled so feed fetches
# do not fail with CERTIFICATE_VERIFY_FAILED (until the Zscaler CA is installed).
if os.environ.get("HTTPS_PROXY"):
    SSL_CTX.check_hostname = False
    SSL_CTX.verify_mode = ssl.CERT_NONE

# total=45s: overall request deadline. connect=20s: TCP handshake timeout.
# sock_read=10s: max time between data chunks (handles slow feeds).
TIMEOUT = aiohttp.ClientTimeout(total=45, connect=20, sock_read=10)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/xml,application/rss+xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
FEED_CONCURRENCY = 5
IMAGE_CONCURRENCY = 5
CYCLE_INTERVAL_SECONDS = 60

_bq = None
_tables_verified = False


def _get_bq():
    global _bq
    if _bq is None:
        credentials, _ = google.auth.default()
        credentials._universe_domain = "googleapis.com"
        _bq = bigquery.Client(project=GCP_PROJECT, credentials=credentials)
    return _bq


def _ensure_dataset_and_tables():
    """Create the BigQuery dataset and tables if they don't already exist."""
    global _tables_verified
    if _tables_verified:
        return
    client = _get_bq()
    dataset_ref = bigquery.DatasetReference(GCP_PROJECT, BQ_DATASET)
    try:
        client.get_dataset(dataset_ref)
        log.info("Dataset %s already exists", BQ_DATASET)
    except Exception:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "EU"
        client.create_dataset(dataset, exists_ok=True)
        log.info("Created dataset %s", BQ_DATASET)

    # --- cloud_news_uris ---
    uris_schema = [
        bigquery.SchemaField("id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("vendor", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("uri", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("frequency", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("criticality", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("last_fetched", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("categories", "STRING", mode="REPEATED"),
    ]
    uris_table = bigquery.Table(SOURCES_TABLE, schema=uris_schema)
    client.create_table(uris_table, exists_ok=True)
    log.info("Table %s ready", SOURCES_TABLE)

    # --- cloud_news_items ---
    items_schema = [
        bigquery.SchemaField("hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("uri_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("title", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("link", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("summary", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("published", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("criticality", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("image_url", "STRING", mode="NULLABLE"),
    ]
    items_table = bigquery.Table(ITEMS_TABLE, schema=items_schema)
    client.create_table(items_table, exists_ok=True)
    log.info("Table %s ready", ITEMS_TABLE)

    _seed_default_feeds(client)

    _tables_verified = True


# ---------- Default feed sources (self-bootstrapping) ----------

_DEFAULT_FEEDS = [
    {"id": 0, "vendor": "AWS", "uri": "https://aws.amazon.com/about-aws/whats-new/recent/feed/", "type": "rss", "frequency": 300, "criticality": 0, "categories": ["product_releases"]},
    {"id": 1, "vendor": "Terraform", "uri": "https://github.com/hashicorp/terraform/releases.atom", "type": "atom", "frequency": 300, "criticality": 50, "categories": ["product_releases"]},
    {"id": 2, "vendor": "Azure", "uri": "https://www.microsoft.com/releasecommunications/api/v2/azure/rss", "type": "rss", "frequency": 300, "criticality": 0, "categories": ["product_releases"]},
    {"id": 3, "vendor": "Google Cloud", "uri": "https://cloud.google.com/feeds/gcp-release-notes.xml", "type": "atom", "frequency": 300, "criticality": 60, "categories": ["product_releases"]},
    {"id": 5, "vendor": "European Council", "uri": "https://www.consilium.europa.eu/en/rss/pressreleases.ashx", "type": "atom", "frequency": 300, "criticality": 1, "categories": ["regulation_compliance"]},
    {"id": 6, "vendor": "NIST", "uri": "https://www.nist.gov/news-events/news/rss.xml", "type": "rss", "frequency": 300, "criticality": 0, "categories": ["regulation_compliance"]},
    {"id": 7, "vendor": "Heise Security", "uri": "https://www.heise.de/security/feed.xml", "type": "atom", "frequency": 300, "criticality": 40, "categories": ["threat_intel"]},
    {"id": 8, "vendor": "BaFin", "uri": "https://www.bafin.de/DE/Service/TopNavigation/RSS/_function/rssnewsfeed.xml", "type": "rss", "frequency": 300, "criticality": 60, "categories": ["regulation_compliance"]},
    {"id": 9, "vendor": "Wired Security", "uri": "https://www.wired.com/feed/category/security/latest/rss", "type": "atom", "frequency": 300, "criticality": 0, "categories": ["threat_intel"]},
    {"id": 10, "vendor": "Security Insider", "uri": "https://www.security-insider.de/rss/news.xml", "type": "atom", "frequency": 300, "criticality": 0, "categories": ["threat_intel"]},
    {"id": 11, "vendor": "cloudvulndb", "uri": "https://www.cloudvulndb.org/rss/feed.xml", "type": "rss", "frequency": 300, "criticality": 80, "categories": ["threat_intel"]},
    {"id": 12, "vendor": "Schneier", "uri": "https://www.schneier.com/feed/atom/", "type": "atom", "frequency": 300, "criticality": 30, "categories": ["threat_intel"]},
    {"id": 13, "vendor": "NSA", "uri": "https://www.nsa.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=1282", "type": "atom", "frequency": 300, "criticality": 0, "categories": ["regulation_compliance"]},
    {"id": 14, "vendor": "IACR", "uri": "https://eprint.iacr.org/rss/rss.xml?order=recent&category=APPLICATIONS,FOUNDATIONS,IMPLEMENTATION,SECRETKEY,PUBLICKEY,ATTACKS", "type": "atom", "frequency": 300, "criticality": 20, "categories": ["research_analysis"]},
    {"id": 15, "vendor": "Krebs on Security", "uri": "https://krebsonsecurity.com/feed/", "type": "atom", "frequency": 300, "criticality": 10, "categories": ["threat_intel"]},
    {"id": 16, "vendor": "Phil Venables", "uri": "https://www.philvenables.com/blog-feed.xml", "type": "atom", "frequency": 300, "criticality": 20, "categories": ["research_analysis"]},
    {"id": 17, "vendor": "Wiz", "uri": "https://www.wiz.io/feed/rss.xml", "type": "rss", "frequency": 300, "criticality": 60, "categories": ["threat_intel"]},
    {"id": 18, "vendor": "Wiz Threats", "uri": "https://www.wiz.io/api/feed/cloud-threat-landscape/rss.xml", "type": "rss", "frequency": 300, "criticality": 90, "categories": ["threat_intel"]},
    {"id": 19, "vendor": "Google Cloud Security Podcast", "uri": "https://cloud.withgoogle.com/cloudsecurity/podcast/feed/", "type": "atom", "frequency": 300, "criticality": 10, "categories": ["threat_intel"]},
    {"id": 20, "vendor": "The Hacker News", "uri": "https://feeds.feedburner.com/TheHackersNews", "type": "atom", "frequency": 300, "criticality": 0, "categories": ["threat_intel"]},
    {"id": 21, "vendor": "Independent Tech", "uri": "https://www.independent.co.uk/tech/rss", "type": "rss", "frequency": 300, "criticality": 0, "categories": ["threat_intel"]},
    {"id": 22, "vendor": "Cloudflare Status", "uri": "https://www.cloudflarestatus.com/history.rss", "type": "rss", "frequency": 300, "criticality": 0, "categories": ["cloud_status"]},
    {"id": 23, "vendor": "IBM Cloud Status", "uri": "https://cloud.ibm.com/status/api/notifications/feed.rss", "type": "rss", "frequency": 300, "criticality": 0, "categories": ["cloud_status"]},
    {"id": 24, "vendor": "Google Cloud Status", "uri": "https://status.cloud.google.com/en/feed.atom", "type": "atom", "frequency": 300, "criticality": 0, "categories": ["cloud_status"]},
    {"id": 25, "vendor": "Azure Status", "uri": "https://azure.status.microsoft/en-us/status/feed/", "type": "atom", "frequency": 300, "criticality": 0, "categories": ["cloud_status"]},
    {"id": 26, "vendor": "AWS Status", "uri": "https://status.aws.amazon.com/rss/all.rss", "type": "rss", "frequency": 300, "criticality": 0, "categories": ["cloud_status"]},
    {"id": 27, "vendor": "CVEfeed High/Critical Severity", "uri": "https://cvefeed.io/rssfeed/severity/high.atom", "type": "atom", "frequency": 300, "criticality": 0, "categories": ["cloud_status"]},
    {"id": 28, "vendor": "Bleeping Computer", "uri": "https://www.bleepingcomputer.com/feed/", "type": "rss", "frequency": 300, "criticality": 50, "categories": ["threat_intel"]},
    {"id": 29, "vendor": "Cyber Security News", "uri": "https://cybersecuritynews.com/feed/", "type": "rss", "frequency": 300, "criticality": 80, "categories": ["threat_intel"]},
    {"id": 30, "vendor": "Dark Reading", "uri": "https://www.darkreading.com/rss.xml", "type": "rss", "frequency": 300, "criticality": 50, "categories": ["threat_intel"]},
    {"id": 31, "vendor": "CSSF", "uri": "https://www.cssf.lu/en/feed/publications", "type": "rss", "frequency": 300, "criticality": 50, "categories": ["regulation_compliance"]},
    {"id": 32, "vendor": "Google Online Security Blog", "uri": "https://feeds.feedburner.com/GoogleOnlineSecurityBlog", "type": "rss", "frequency": 300, "criticality": 50, "categories": ["threat_intel"]},
    {"id": 9999, "vendor": "CISO/ICTR Office", "uri": "ciso://manual-entry", "type": "manual", "frequency": 999999999, "criticality": 100, "categories": ["internal"]},
]


def _seed_default_feeds(client):
    """Insert default feed sources if the table is empty (self-bootstrapping)."""
    count_query = f"SELECT COUNT(*) as cnt FROM `{SOURCES_TABLE}`"
    result = list(client.query(count_query).result())
    if result[0].cnt > 0:
        return

    log.info("Seeding %d default feed sources into %s", len(_DEFAULT_FEEDS), SOURCES_TABLE)
    rows = []
    for feed in _DEFAULT_FEEDS:
        rows.append({
            "id": feed["id"],
            "vendor": feed["vendor"],
            "uri": feed["uri"],
            "type": feed["type"],
            "frequency": feed["frequency"],
            "criticality": feed["criticality"],
            "categories": feed["categories"],
        })
    errors = client.insert_rows_json(SOURCES_TABLE, rows)
    if errors:
        log.error("Seed insert errors: %s", errors)
    else:
        log.info("Successfully seeded %d feed sources", len(rows))


def get_feed_sources():
    query = f"""
        SELECT * FROM `{SOURCES_TABLE}`
        WHERE last_fetched IS NULL
           OR TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), last_fetched, SECOND) >= frequency
    """
    return list(_get_bq().query(query).result())


def get_existing_hashes():
    query = f"SELECT `hash` FROM `{ITEMS_TABLE}` WHERE `published` >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)"
    return {row.hash for row in _get_bq().query(query).result()}


def update_fetch_timestamps(source_ids):
    if not source_ids:
        return
    query = f"""
        MERGE `{SOURCES_TABLE}` T
        USING (SELECT source_id FROM UNNEST(@ids) AS source_id) S
        ON T.id = S.source_id
        WHEN MATCHED THEN UPDATE SET last_fetched = CURRENT_TIMESTAMP()
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("ids", "INTEGER", source_ids)]
    )
    try:
        _get_bq().query(query, job_config=config).result()
        log.info("Updated last_fetched for %d sources", len(source_ids))
    except Exception as e:
        log.error("Timestamp update failed: %s", e)


def save_articles(articles):
    if not articles:
        return
    try:
        errors = _get_bq().insert_rows_json(ITEMS_TABLE, articles)
        if errors:
            log.error("Insert errors: %s", errors)
        else:
            log.info("Inserted %d articles", len(articles))
    except Exception as e:
        log.error("Insert failed: %s", e)


async def fetch_feed(source, session, semaphore):
    try:
        async with semaphore:
            log.info("Fetching %s", source.uri)
            async with session.get(
                source.uri, headers=HEADERS, allow_redirects=True
            ) as resp:
                resp.raise_for_status()
                data = await resp.read()
        feed = await asyncio.to_thread(feedparser.parse, data)
        if feed.bozo:
            log.warning("Parse warning for %s: %s", source.uri, feed.bozo_exception)
            return None
        return {
            "id": source.id,
            "vendor": source.vendor,
            "criticality": source.criticality,
            "data": feed,
        }
    except Exception as e:
        log.error("Feed error %s: %r", source.uri, e)
        return None


async def parse_article(item, feed_id, criticality, cutoff, session, sem):
    ts = item.get("published_parsed") or item.get("updated_parsed")
    published = (
        datetime(*ts[:6], tzinfo=timezone.utc) if ts else datetime.now(timezone.utc)
    )
    if published < cutoff:
        return None

    link = item.get("link", "N/A")
    guid = item.get("id") or item.get("guid") or link

    async with sem:
        image_url = await get_item_image_url(item, session)

    return {
        "hash": hashlib.md5(f"{feed_id}{guid}".encode()).hexdigest(),
        "uri_id": feed_id,
        "title": item.get("title", "N/A"),
        "link": link,
        "summary": item.get("summary", item.get("description", "N/A")),
        "published": published.isoformat(),
        "criticality": criticality,
        "image_url": image_url,
    }


async def extract_articles(feed_info, existing_hashes, session, image_sem):
    entries = feed_info["data"].get("entries", [])
    if not entries:
        return []

    # Limit to 7-day window: older articles assumed already parsed
    # Keeps duplicate-detection hash set smaller
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=1)
    parsed = await asyncio.gather(
        *(
            parse_article(
                e, feed_info["id"], feed_info["criticality"], cutoff, session, image_sem
            )
            for e in entries
        )
    )

    new = []
    for article in parsed:
        if not article or article["hash"] in existing_hashes:
            continue
        existing_hashes.add(article["hash"])
        log.info("New: %s (%s)", article["title"], feed_info["vendor"])
        new.append(article)
    return new


async def process_cycle(session):
    log.info("Starting news cycle")
    start = time.monotonic()

    await asyncio.to_thread(_ensure_dataset_and_tables)

    sources, hashes = await asyncio.gather(
        asyncio.to_thread(get_feed_sources),
        asyncio.to_thread(get_existing_hashes),
    )

    if not sources:
        log.info("No feeds due — cycle complete")
        return

    feed_sem = asyncio.Semaphore(FEED_CONCURRENCY)
    image_sem = asyncio.Semaphore(IMAGE_CONCURRENCY)

    feeds = await asyncio.gather(*(fetch_feed(s, session, feed_sem) for s in sources))

    fetched_ids, tasks = [], []
    for f in feeds:
        if f:
            fetched_ids.append(f["id"])
            tasks.append(extract_articles(f, hashes, session, image_sem))

    all_articles = [a for batch in await asyncio.gather(*tasks) for a in batch]

    await asyncio.gather(
        asyncio.to_thread(update_fetch_timestamps, fetched_ids),
        asyncio.to_thread(save_articles, all_articles),
    )

    log.info(
        "Cycle done in %.2fs — %d new articles",
        time.monotonic() - start,
        len(all_articles),
    )


async def run_once():
    connector = aiohttp.TCPConnector(
        limit_per_host=10, ttl_dns_cache=300, ssl=SSL_CTX, force_close=False
    )
    async with aiohttp.ClientSession(
        connector=connector, timeout=TIMEOUT, trust_env=True
    ) as session:
        await process_cycle(session)


async def run_forever():
    connector = aiohttp.TCPConnector(
        limit_per_host=10, ttl_dns_cache=300, ssl=SSL_CTX, force_close=False
    )
    async with aiohttp.ClientSession(
        connector=connector, timeout=TIMEOUT, trust_env=True
    ) as session:
        while True:
            try:
                await process_cycle(session)
            except Exception:
                log.exception("Cycle failed")
            await asyncio.sleep(CYCLE_INTERVAL_SECONDS)


async def serve():
    app = web.Application()
    app.add_routes([web.get("/health", lambda _: web.Response(text="OK"))])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Health server on port %d", port)
    await run_forever()


if __name__ == "__main__":
    try:
        if "--serve" in sys.argv:
            asyncio.run(serve())
        else:
            asyncio.run(run_once())
    except KeyboardInterrupt:
        log.info("Shutting down")
