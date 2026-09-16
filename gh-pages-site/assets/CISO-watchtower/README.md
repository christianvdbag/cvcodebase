# CISO Watchtower LIVE

> **Real-time information security intelligence dashboard for Deutsche Börse Group**

**[🔗 Open Live Dashboard](https://ciso-watchtower-webapp-96825836981.europe-west3.run.app/)**

CISO Watchtower LIVE aggregates, processes, and displays cybersecurity, regulatory, and risk news from 30+ trusted global sources into a single continuously-updating stream. It is a core component of the DBG security situational awareness ecosystem and serves as a live news input for [CISO Watchtower](https://knowledge.deutsche-boerse.de/spaces/ICTR/pages/685310827/CISO+watchtower+Live).

---

## Architecture

The platform is composed of two independently deployed services backed by Google BigQuery.

```
┌─────────────────────────────────────┐
│         External RSS / Atom          │
│  (AWS, Azure, GCP, NIST, NSA, ...)  │
└──────────────────┬──────────────────┘
                   │ fetch (aiohttp)
                   ▼
     ┌─────────────────────────┐
     │    News Processor        │   Cloud Run Job
     │  news_processor/         │   runs every 60 s
     │  • fetch feeds           │
     │  • deduplicate (MD5)     │
     │  • resolve images        │
     └──────────┬──────────────┘
                │ INSERT
                ▼
     ┌─────────────────────────┐
     │        BigQuery          │
     │  cloud_news_uris         │  feed source registry
     │  cloud_news_items        │  article store
     └──────────┬──────────────┘
                │ SELECT (ranked window)
                ▼
     ┌─────────────────────────┐
     │        Web App           │   Cloud Run Service
     │  webapp/                 │
     │  • Flask + Gunicorn      │
     │  • /api/items            │
     │  • /api/categories       │
     └──────────┬──────────────┘
                │ JSON API
                ▼
     ┌─────────────────────────┐
     │         Browser          │
     │  Tailwind CSS + Vanilla  │
     │  auto-scroll, filter,    │
     │  priority scoring        │
     └─────────────────────────┘
```

### BigQuery Schema

**`cloud_news_uris`** — feed source registry

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `vendor` | STRING | Source name (e.g. `AWS`, `NIST`) |
| `uri` | STRING | RSS / Atom feed URL |
| `type` | STRING | `rss` or `atom` |
| `frequency` | INTEGER | Poll interval in seconds |
| `criticality` | INTEGER | Base priority score (0–100) |
| `last_fetched` | TIMESTAMP | Last successful poll time |
| `categories` | ARRAY\<STRING\> | Topic tags |

**`cloud_news_items`** — article store

| Column | Type | Description |
|---|---|---|
| `hash` | STRING | MD5 deduplication key (`feed_id + guid`) |
| `uri_id` | INTEGER | FK → `cloud_news_uris.id` |
| `title` | STRING | Article headline |
| `link` | STRING | Article URL |
| `summary` | STRING | Article description / body excerpt |
| `published` | TIMESTAMP | Publication timestamp (UTC) |
| `criticality` | INTEGER | Inherited from source |
| `image_url` | STRING | Hero image (media tag or OG scrape) |

---

## Repository Structure

```
CISO-watchtower/
├── webapp/                  # Flask web app (Cloud Run Service)
│   ├── app.py               # Routes: /, /api/items, /api/categories
│   ├── Dockerfile           # Multi-stage: Tailwind build → Flask image
│   ├── mock_data.py         # Local dev only — mock items and categories
│   ├── templates/
│   │   └── index.html       # Dashboard SPA
│   └── static/
│       ├── css/             # Tailwind input + compiled output
│       └── js/
│           └── script.js    # Auto-scroll, priority scoring, category filter
│
├── news_processor/          # Async feed processor (Cloud Run Job)
│   ├── news_processor.py    # Fetch → parse → deduplicate → insert loop
│   ├── image_utils.py       # Hero image resolver (media tags + OG scrape)
│   └── Dockerfile
│
├── tests/                   # pytest suite (35 tests, no GCP credentials needed)
│   ├── conftest.py
│   ├── test_webapp.py
│   ├── test_news_processor.py
│   └── requirements.txt
│
└── confluence-mcp/          # Confluence MCP server (developer tooling)
```

---

## Services

### News Processor (`news_processor/`)

A Python `asyncio` service that runs on a **60-second cycle**:

1. Reads `cloud_news_uris` for sources due to be fetched (based on `frequency` and `last_fetched`).
2. Fetches feeds concurrently (up to 5 at a time) using `aiohttp` + `feedparser`.
3. For each article resolves a hero image: media content tags → OG/Twitter card scrape.
4. Deduplicates against the last 7 days of hashes already in BigQuery.
5. Batch-inserts new articles to `cloud_news_items` and updates `last_fetched` timestamps.

**Key settings** (via environment variables):

| Variable | Default | Description |
|---|---|---|
| `GCP_PROJECT` | _(required)_ | GCP project ID |
| `BQ_DATASET` | `cloud_news` | BigQuery dataset |
| `HTTPS_PROXY` | — | Corporate proxy (`squid-proxy.gcp.dbgcloud.io:3128`) |

### Web App (`webapp/`)

A **Flask + Gunicorn** application that serves the dashboard and two JSON API endpoints:

- `GET /api/items` — Returns up to 100 latest articles (at most `MAX_PER_SOURCE` per feed), with category metadata joined from `cloud_news_uris`.
- `GET /api/categories` — Returns all distinct category tags for the filter UI.

The frontend (`script.js`) polls `/api/items` every 10 seconds and:
- Calculates a **priority score** = `criticality × 0.95^hours_old` (time-decaying).
- Shows the top-priority article in a spotlight panel (auto-advancing every ~30 s with a progress bar).
- Renders the remaining items in a smooth auto-scrolling vertical ticker.
- Supports **category filtering**, **scroll-speed control** (Slow / Medium / Fast), and **pause on hover**.

**Color-coded severity:**

| Color | Criticality |
|---|---|
| Purple | ≥ 100 (critical) |
| Red | ≥ 80 |
| Amber | ≥ 50 |
| Teal | < 50 |

**Key settings:**

| Variable | Default | Description |
|---|---|---|
| `GCP_PROJECT` | _(required)_ | GCP project ID |
| `BQ_DATASET` | `cloud_news` | BigQuery dataset |
| `MAX_PER_SOURCE` | `10` | Max articles per source in API response |
| `PORT` | `8080` | HTTP listen port |

---

## News Sources

30+ RSS and Atom feeds across cloud, security, and regulatory topics:

| Category | Sources |
|---|---|
| Cloud providers | AWS What's New, Azure Release Comms, Google Cloud Release Notes, Terraform |
| Security news | The Hacker News, Krebs on Security, Bleeping Computer, Dark Reading, Wired Security, Heise Security, Cyber Security News |
| Threat intelligence | NSA, NIST, Wiz Threat Landscape, cloudvulndb, CVEfeed (High/Critical) |
| Research / blogs | Schneier on Security, Phil Venables, IACR ePrint, Google Security Blog, Chromium Blog, Google Cloud Security Podcast |
| Regulatory | BaFin, European Council |
| Cloud status | AWS Status, Azure Status, GCP Status, Cloudflare Status, IBM Cloud Status |

Sources are managed directly in the `cloud_news_uris` BigQuery table (no redeploy needed to add/remove feeds).

---

## CI/CD

Both services have independent GitHub Actions pipelines that trigger on push to `master` within their respective directories.

```
push to master
  └── webapp/**          → Webapp CI/CD
  └── news_processor/**  → News Processor CI/CD
```

Each pipeline:
1. Builds the Docker image.
2. Pushes to **JFrog Artifactory** (internal registry).
3. Promotes to **GCP Artifact Registry** (`grc-docker`).
4. Deploys to **GCP Cloud Run** (Service for webapp, Job for news processor).

Image tags follow the pattern `<service>-YYYYMMDD-<git-sha7>`.

**Required repository secrets:**

| Secret | Used for |
|---|---|
| `GCP_PROJECT` | GCP project ID |
| `GCP_REGION` | Cloud Run deployment region |
| `GCP_SERVICE_ACCOUNT_JSON` | GCP auth for deploy |
| `ARTIFACTORY_NAME` | JFrog registry hostname |
| `ARTIFACTORY_USERNAME` | JFrog credentials |
| `ARTIFACTORY_PASSWORD` | JFrog credentials |

---

## Local Development

### Prerequisites

- Python 3.11+
- Node 20+ (for Tailwind CSS compilation)
- GCP credentials with BigQuery read/write access

### Webapp

**Without BigQuery** (mock data, no GCP credentials needed):
```bash
cd webapp
pip install -r requirements.txt
npm install tailwindcss @tailwindcss/cli
npx @tailwindcss/cli -i ./static/css/input.css -o ./static/css/output.css

USE_MOCK_ITEMS=true python app.py
# → http://localhost:8080
```

**With real BigQuery**:
```bash
export GCP_PROJECT=your-project-id
python app.py
```

### News Processor

```bash
cd news_processor
pip install -r requirements.txt

export GCP_PROJECT=your-project-id
python news_processor.py        # runs one cycle then exits
python news_processor.py --serve  # continuous loop + /health endpoint
```

Copy `.env.example` to `.env` and populate values (including the corporate proxy) when running inside the DBG network.

---

## Running Tests

**Run the full test suite before opening a pull request.** Tests cover Flask routes, BigQuery caching correctness, error handling, article parsing, and deduplication. No GCP credentials or network access are required.

### Setup (one-time)

```bash
pip install -r webapp/requirements.txt
pip install -r news_processor/requirements.txt
pip install -r tests/requirements.txt
```

### Run

```bash
pytest
```

All 35 tests should pass. If any fail, fix the issue before opening a PR.

```
35 passed in 1.92s
```

---

## Code Formatting

Python code in this repository must be formatted with Black before committing.

```bash
black webapp news_processor tests
```

Run Black after making Python changes and before opening a pull request.

---

## Known Limitations & Production Considerations

| Area | Detail |
|---|---|
| **Per-instance cache scope** | `/api/items` is cached in-process with a 30 s TTL, so not every request hits BigQuery. However, cache state is not shared across Cloud Run instances/workers, so at higher scale each instance can still issue periodic BigQuery queries. Consider a shared cache layer if query volume or cost becomes significant. |
| **Gunicorn threads** | Currently `--workers 2 --threads 4`. Each BigQuery call blocks a thread for ~1–2 s. Increase threads (`--threads 8`) or use `gevent` workers under high concurrent load. |
| **Corporate proxy** | `HTTPS_PROXY` and `NO_PROXY` must be set in the Cloud Run Job environment variables — they are not set automatically from `.env.example`. |
| **Favicons** | The frontend uses `www.google.com/s2/favicons` to resolve source icons. Verify this external URL is reachable from the browser inside the DBG network (e.g. on CISO office screens). |
| **Category definitions duplicated** | Category display labels are defined in both `webapp/mock_data.py` (Python) and `webapp/static/js/script.js` (JavaScript). When adding a new category to `cloud_news_uris`, both files must be updated. |
| **`mock_data.py` in production image** | The Dockerfile copies `mock_data.py` into the production image unconditionally. It is harmless but unused in production (`USE_MOCK_ITEMS` defaults to `false`). |

---

## Roadmap

Roadmap details are maintained in Confluence and are the source of truth:

- [CISO Watchtower Live Roadmap (Confluence)](https://knowledge.deutsche-boerse.de/spaces/ICTR/pages/685310827/CISO+watchtower+Live)

Current focus areas:

- Stabilization and quality improvements for the v2.1 production baseline
- Operational hardening and scalability improvements
- UX enhancements for dashboard usability and filtering

---

## Versioning

Current version: **2.1**

- Versioning uses `major.minor.patch` semantics.
- Release planning and future version targets are tracked in Confluence.
- Release history and change details should be documented in release notes / changelog entries.

---

## Links

- [Confluence page — CISO Watchtower Live](https://knowledge.deutsche-boerse.de/spaces/ICTR/pages/685310827/CISO+watchtower+Live)
