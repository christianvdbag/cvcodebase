import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin

_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def _as_list(val):
    return [val] if isinstance(val, dict) else val


async def _scrape_og_image(url: str, session: aiohttp.ClientSession) -> str | None:
    if not url:
        return None
    try:
        async with session.get(url, headers=_SCRAPE_HEADERS, timeout=10) as resp:
            resp.raise_for_status()
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for attrs in ({"property": "og:image"}, {"name": "twitter:image"}):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return urljoin(url, tag["content"])
    except Exception:
        pass
    return None


async def get_item_image_url(entry: dict, session: aiohttp.ClientSession) -> str | None:
    link = entry.get("link")

    for mc in _as_list(entry.get("media_content", [])):
        if mc.get("type", "").startswith("image/") and (u := mc.get("url")):
            return urljoin(link, u)

    for mt in _as_list(entry.get("media_thumbnail", [])):
        if u := mt.get("url"):
            return urljoin(link, u)

    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image/") and (u := enc.get("href")):
            return urljoin(link, u)

    for lo in entry.get("links", []):
        if (
            lo.get("rel") == "enclosure"
            and lo.get("type", "").startswith("image/")
            and (u := lo.get("href"))
        ):
            return urljoin(link, u)

    return await _scrape_og_image(link, session)
