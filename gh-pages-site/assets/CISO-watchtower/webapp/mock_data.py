"""Mock data for local testing without BigQuery access."""

from datetime import datetime, timedelta, timezone

CATEGORY_METADATA = {
    "threat_intel": {"display_name": "Threat Intel", "sort_order": 1},
    "research_analysis": {"display_name": "Research & Analysis", "sort_order": 2},
    "cloud_status": {"display_name": "Cloud Status", "sort_order": 3},
    "product_releases": {"display_name": "Product Releases", "sort_order": 4},
    "regulation_compliance": {
        "display_name": "Regulation & Compliance",
        "sort_order": 5,
    },
    "internal": {"display_name": "Internal", "sort_order": 6},
}


def build_mock_items():
    """Generate realistic mock news items for testing."""
    now = datetime.now(timezone.utc)

    _TEMPLATES = [
        {
            "uri_id": 28,
            "vendor": "BleepingComputer",
            "categories": ["threat_intel"],
            "criticality": 50,
            "title": "New Windows 11 emergency update fixes preview update install issues",
            "link": "https://www.bleepingcomputer.com/news/microsoft/new-windows-11-kb5086672-emergency-update-fixes-install-issues/",
            "summary": "Microsoft released an emergency update to fix the March 2026 KB5079391 non-security preview update, which was pulled over the weekend due to installation issues. [...]",
            "image_url": "https://www.bleepstatic.com/content/hl-images/2026/04/01/Windows-11.jpg",
        },
        {
            "uri_id": 10,
            "vendor": "Security Insider",
            "categories": ["threat_intel"],
            "criticality": 80,
            "title": "Oracle schließt RCE-Schwachstelle in Fusion Middleware",
            "link": "https://www.security-insider.de/oracle-kritische-rce-luecke-identity-manager-a-28d02c8a1a0974a0badc66a15191cf32/",
            "summary": "Oracle schlie&szlig;t eine kritische Sicherheitsl&uuml;cke in Identity Manager und Web Services Manager. Entfernte Angreifer k&ouml;nnen ohne Authentifizierung Schadcode ausf&uuml;hren.",
            "image_url": "https://static.independent.co.uk/2026/04/01/4/43/The-Oracle-logo-is-displayed-in-front-of-an-Oracle-campus-in-Redwood-Shores-California.jpeg?width=1200&auto=webp&crop=3%3A2",
        },
        {
            "uri_id": 22,
            "vendor": "Cloudflare Status",
            "categories": ["cloud_status"],
            "criticality": 0,
            "title": "ORD (Chicago) scheduled maintenance on 2026-04-01",
            "link": "https://www.cloudflarestatus.com/incidents/sq9q64y20x2b",
            "summary": "<p><strong>SCHEDULED EVENT Apr 1, 06:00&ndash;12:00 UTC</strong></p><p>We will be performing scheduled maintenance in the ORD (Chicago) datacenter. Traffic might be re-routed, causing a slight increase in latency for end-users in the affected region.</p>",
            "image_url": "https://dka575ofm4ao0.cloudfront.net/assets/logos/favicon-2b86ed00cfa6258307d4a3d0c482fd733c7973f82de213143b24fc062c540367.png",
        },
        {
            "uri_id": 7,
            "vendor": "Heise",
            "categories": ["threat_intel"],
            "criticality": 40,
            "title": "Jetzt aktualisieren! Chrome-Sicherheitslücke wird angegriffen",
            "link": "https://www.heise.de/news/Jetzt-aktualisieren-Chrome-Sicherheitsluecke-wird-angegriffen-11242653.html",
            "summary": "Google hat ein Update f&uuml;r Chrome ver&ouml;ffentlicht. Es stopft 21 Sicherheitsl&uuml;cken. Angriffe laufen auf eine Codeschmuggel-L&uuml;cke.",
            "image_url": "https://heise.cloudimg.io/bound/1200x1200/q85.png-lossy-85.webp-lossy-85.foil1/_www-heise-de_/imgs/18/5/0/5/6/1/9/1/2026-03-14-Chrome_SIcherheitsluecke-75e9a08263c241ca.png",
        },
        {
            "uri_id": 1,
            "vendor": "CISA",
            "categories": ["regulation_compliance"],
            "criticality": 100,
            "title": "CISA Adds Three Known Exploited Vulnerabilities to Catalog",
            "link": "https://www.cisa.gov/news-events/alerts/2026/04/01/cisa-adds-three-known-exploited-vulnerabilities-catalog",
            "summary": "<p>CISA has added three new vulnerabilities to its <a href='https://www.cisa.gov/known-exploited-vulnerabilities-catalog'>Known Exploited Vulnerabilities Catalog</a>, based on evidence of active exploitation. These vulnerabilities are frequent attack vectors for malicious cyber actors and pose significant risks to the federal enterprise.</p>",
            "image_url": "https://www.cisa.gov/profiles/cisad8_gov/themes/custom/cisad8/images/cisa-logo-small.png",
        },
        {
            "uri_id": 5,
            "vendor": "Krebs on Security",
            "categories": ["threat_intel"],
            "criticality": 40,
            "title": "Ransomware Group Claims Breach of Major European Bank",
            "link": "https://krebsonsecurity.com/2026/04/ransomware-group-claims-breach-of-major-european-bank/",
            "summary": "A ransomware group has claimed responsibility for a breach at a major European financial institution, threatening to publish stolen data unless a ransom is paid within 72 hours.",
            "image_url": "https://krebsonsecurity.com/wp-content/uploads/2010/02/krebsonsecurity-logo.png",
        },
        {
            "uri_id": 15,
            "vendor": "Microsoft Security Blog",
            "categories": ["regulation_compliance"],
            "criticality": 80,
            "title": "Patch Tuesday April 2026: 147 CVEs including 3 zero-days",
            "link": "https://www.microsoft.com/en-us/security/blog/2026/04/01/patch-tuesday-april-2026/",
            "summary": "<p>Today, Microsoft released security updates addressing 147 CVEs, including three zero-day vulnerabilities actively exploited in the wild. Administrators are urged to prioritize patching CVE-2026-28311 (CVSS 9.8), a critical remote code execution flaw in Windows Print Spooler.</p>",
            "image_url": "https://www.microsoft.com/en-us/security/blog/wp-content/uploads/2023/09/Microsoft-Security-Blog.png",
        },
        {
            "uri_id": 21,
            "vendor": "The Independent",
            "categories": ["product_releases"],
            "criticality": 0,
            "title": "'Today is your last working day': Oracle lays off thousands in massive AI pivot",
            "link": "https://www.independent.co.uk/tech/oracle-layoff-ai-data-centre-b2949704.html",
            "summary": "<p>Laid off workers were informed of their job status in an early morning email as Oracle accelerates its shift toward AI infrastructure.</p>",
            "image_url": "https://static.independent.co.uk/2026/04/01/4/43/The-Oracle-logo-is-displayed-in-front-of-an-Oracle-campus-in-Redwood-Shores-California.jpeg?width=1200&auto=webp&crop=3%3A2",
        },
        {
            "uri_id": 10,
            "vendor": "Security Insider",
            "categories": ["research_analysis"],
            "criticality": 0,
            "title": "KI-Patch-Dienst stuft Schwachstelle fatal falsch ein",
            "link": "https://www.security-insider.de/llm-falsche-priorisierung-rce-ticket-low-critical-a-c5de65fa74f6df41233b76be4ed05e85/",
            "summary": "Ein automatisierter Severity-Vorschlag eines integrierten LLM-Assistenten hat ein Ticket als niedriger priorisiert, obwohl sich das Incident-Team sp&auml;ter auf eine deutlich h&ouml;here Gef&auml;hrdung einigte.",
            "image_url": None,
        },
        {
            "uri_id": 7,
            "vendor": "Heise",
            "categories": ["research_analysis"],
            "criticality": 40,
            "title": "Passwort Folge 54: Alte Bugs, neue Angriffe und zukünftige PKI",
            "link": "https://www.heise.de/news/Passwort-Folge-54-Alte-Bugs-neue-Angriffe-und-zukuenftige-PKI-11208348.html",
            "summary": "Im Podcast geht es um k&uuml;rzlich entdeckte L&uuml;cken in uraltem Unix, aktuelle Angriffe auf Apple-Ger&auml;te, quantensichere Zertifikate f&uuml;rs Web und einiges mehr.",
            "image_url": "https://heise.cloudimg.io/bound/1200x1200/q85.png-lossy-85.webp-lossy-85.foil1/_www-heise-de_/imgs/18/5/0/4/4/0/0/5/heise_Podxast_Security_16_9_AudioV2__1_-97cfb898e5203c1c.jpg",
        },
        {
            "uri_id": 3,
            "vendor": "AWS Status",
            "categories": ["cloud_status"],
            "criticality": 0,
            "title": "AWS us-east-1: Elevated error rates for Amazon S3",
            "link": "https://status.aws.amazon.com/incidents/us-east-1-s3",
            "summary": "<p>We are investigating elevated error rates for Amazon S3 in the US-EAST-1 region. Customers may experience increased latency or failures when accessing S3 objects. We will provide an update within 30 minutes.</p>",
            "image_url": None,
        },
        {
            "uri_id": 2,
            "vendor": "NVD",
            "categories": ["regulation_compliance"],
            "criticality": 100,
            "title": "CVE-2026-1337 — Critical Auth Bypass in FortiGate SSL-VPN",
            "link": "https://nvd.nist.gov/vuln/detail/CVE-2026-1337",
            "summary": "An authentication bypass vulnerability in Fortinet FortiOS SSL-VPN allows a remote unauthenticated attacker to obtain a super-admin session via crafted HTTP requests. CVSS v3 Base Score: 9.8 CRITICAL.",
            "image_url": None,
        },
    ]

    items = []
    for i, tpl in enumerate(_TEMPLATES):
        # Spread items across multiple days so date dividers are visible
        if i < 4:
            offset = timedelta(minutes=i * 7)  # today
        elif i < 8:
            offset = timedelta(days=1, minutes=i * 7)  # yesterday
        else:
            offset = timedelta(days=2, minutes=i * 7)  # 2 days ago
        items.append(
            {
                "hash": f"mock-{tpl['uri_id']:02d}-{i:03d}",
                "uri_id": tpl["uri_id"],
                "vendor": tpl["vendor"],
                "categories": tpl["categories"],
                "criticality": tpl["criticality"],
                "title": tpl["title"],
                "link": tpl["link"],
                "summary": tpl["summary"],
                "published": (now - offset).isoformat().replace("+00:00", "Z"),
                "image_url": tpl["image_url"],
            }
        )
    return items


def build_mock_categories(items):
    """Extract unique canonical category keys from mock items."""
    canonical_keys = set()
    for item in items:
        for cat_key in item.get("categories") or []:
            if isinstance(cat_key, str) and cat_key.strip():
                canonical_keys.add(cat_key)

    # Return sorted canonical keys so filtering works with the items' category keys
    return sorted(canonical_keys)
