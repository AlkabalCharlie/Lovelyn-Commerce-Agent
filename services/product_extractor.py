"""Tiered product extraction - closes the manual-seed gap.

Try in order; first non-thin result wins:
  Tier 1: existing meta/OpenGraph parse (unchanged behavior).
  Tier 2: JSON-LD (<script type="application/ld+json">), microdata
          (itemprop), and embedded state (__NEXT_DATA__/window.__*).
  Tier 3: headless render via Playwright (chromium, headless); single
          attempt, per-page timeout, no retry-storm; SSRF guard kept.
  Tier 4: thin/None -> caller saves with manual fallback (rare now).

FACT-LOCK: extract ONLY what the page literally contains. Prices come from
structured offer fields ONLY - never inferred from prose. A missing price
stays missing (caller seeds), never invented.
"""
import json
import logging
import re

import requests
from bs4 import BeautifulSoup

from core.exceptions import ExtractionError
from services.url_safety import check_url_safety

logger = logging.getLogger(__name__)

_THIN_DESCRIPTION_LEN = 80

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(str(text).split())
    return cleaned[:500] if cleaned else None


def _thin(result: dict) -> bool:
    desc = (result.get("description") or "").strip()
    return len(desc) < _THIN_DESCRIPTION_LEN or not result.get("description")


# ---------------------------------------------------------------------------
# Tier 2: structured data (JSON-LD, microdata, embedded state)
# ---------------------------------------------------------------------------

def _price_from_offer(obj: dict) -> str | None:
    """Price from a structured offer ONLY (schema.org style). Never prose."""
    offer = obj.get("offers") or {}
    if isinstance(offer, list) and offer:
        offer = offer[0]
    if not isinstance(offer, dict):
        return None
    price = offer.get("price") or offer.get("lowPrice") or offer.get("highPrice")
    if price is None or str(price).strip() == "":
        return None
    return str(price).strip()


def _from_jsonld(soup: BeautifulSoup) -> dict:
    out = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        nodes = data.get("@graph", []) if isinstance(data, dict) and "@graph" in data else (
            data if isinstance(data, list) else [data])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if "name" in node and not out.get("title"):
                out["title"] = _clean(node["name"])
            if "description" in node and not out.get("description"):
                out["description"] = _clean(node["description"])
            price = _price_from_offer(node)
            if price and not out.get("price"):
                out["price"] = price
    return out


def _from_microdata(soup: BeautifulSoup) -> dict:
    out = {}
    el = soup.find(attrs={"itemprop": "name"}) or soup.find("h1")
    if el:
        out["title"] = _clean(el.get_text() if el.name != "meta" else el.get("content"))
    el = soup.find(attrs={"itemprop": "description"})
    if el:
        out["description"] = _clean(
            el.get_text() if el.name != "meta" else el.get("content"))
    el = soup.find(attrs={"itemprop": "price"})
    if el:
        content = el.get("content") if el.name == "meta" else el.get_text()
        if content and re.fullmatch(r"\d+(\.\d{1,2})?", content.strip()):
            out["price"] = content.strip()  # microdata price = structured offer
    return out


def _from_embedded_state(html: str) -> dict:
    """__NEXT_DATA__ / window.__* blobs: price from structured offer fields
    ONLY. We look at JSON keys like price/priceAmount/offer, never prose."""
    out = {}
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            props = (data.get("props") or {}).get("pageProps") or {}
            for key in ("product", "offer", "data"):
                node = props.get(key)
                if isinstance(node, dict):
                    if node.get("name") and not out.get("title"):
                        out["title"] = _clean(node["name"])
                    if node.get("description") and not out.get("description"):
                        out["description"] = _clean(node["description"])
                    price = _price_from_offer(node)
                    if price and not out.get("price"):
                        out["price"] = price
        except (json.JSONDecodeError, AttributeError):
            pass
    # Generic window.__* JSON - only exact numeric price keys, no prose.
    if not out.get("price"):
        m = re.search(r'window\.__[A-Z_]+\s*=\s*(\{.*?\});', html)
        if m:
            try:
                blob = json.loads(m.group(1))
                def find_offer(node):
                    if isinstance(node, dict):
                        if "price" in node and isinstance(node["price"], (int, float)):
                            return node["price"]
                        if "offers" in node and isinstance(node["offers"], dict):
                            p = node["offers"].get("price")
                            if isinstance(p, (int, float)):
                                return p
                        for v in node.values():
                            found = find_offer(v)
                            if found is not None:
                                return found
                    elif isinstance(node, list):
                        for item in node:
                            found = find_offer(item)
                            if found is not None:
                                return found
                    return None
                price = find_offer(blob)
                if price is not None and float(price) > 0:
                    out["price"] = str(price)
            except (json.JSONDecodeError, AttributeError, ValueError):
                pass
    return out


def _extract_tier2(soup: BeautifulSoup, html: str) -> dict:
    result = {}
    for source in (_from_jsonld(soup), _from_microdata(soup), _from_embedded_state(html)):
        for key, value in source.items():
            if value and not result.get(key):
                result[key] = value
    return result


# ---------------------------------------------------------------------------
# Tier 3: headless render
# ---------------------------------------------------------------------------

def _extract_tier3(url: str, timeout_ms: int = 20000) -> dict:
    """Headless chromium render, single attempt, no retry storm."""
    if not PLAYWRIGHT_AVAILABLE:
        logger.info("Playwright not installed - tier 3 skipped.")
        return {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                title = page.title() or None
                body_text = page.inner_text("body")
                # Price-bearing elements only: structured classes/attributes,
                # never prose numbers from the whole body.
                price_text = None
                for sel in ("[itemprop=price]", ".price", "[class*=price]",
                            "[data-price]", "[class*=Price]"):
                    el = page.query_selector(sel)
                    if el:
                        candidate = el.inner_text() or el.get_attribute("content") or ""
                        candidate = candidate.strip()
                        m = re.search(r"\d+(?:\.\d{1,2})?", candidate)
                        if m:
                            price_text = m.group(0)
                            break
                description = None
                meta = page.query_selector('meta[name=description], meta[property="og:description"]')
                if meta:
                    description = (meta.get_attribute("content") or "").strip() or None
                if not description and body_text:
                    description = body_text[:500]
                return {
                    "title": _clean(title),
                    "description": _clean(description),
                    "price": price_text,
                }
            finally:
                browser.close()
    except (PWTimeout, Exception) as exc:
        logger.info("Tier 3 render failed for %s: %s", url, type(exc).__name__)
        return {}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_product_data_tiered(url: str, playwright_enabled: bool = True) -> dict:
    """Tier 1 -> Tier 2 -> Tier 3 -> Tier 4 (thin). First non-thin wins."""
    check_url_safety(url)

    headers = {"User-Agent": "LovelynBot/1.0 (Commerce Intelligence Agent)"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ExtractionError(f"Network error while fetching URL: {e}")

    soup = BeautifulSoup(response.text, "html.parser")

    # Tier 1: meta/OpenGraph (existing logic, fact-locked)
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image["content"].strip()

    description = None
    for prop in (("property", "og:description"), ("name", "description")):
        tag = soup.find("meta", attrs={prop[0]: prop[1]})
        if tag and tag.get("content"):
            description = tag["content"].strip()[:500]
            break

    price = None
    price_tag = (
        soup.find("meta", property="product:price:amount")
        or soup.find("meta", property="og:price:amount")
        or soup.find(attrs={"itemprop": "price"})
    )
    if price_tag and price_tag.get("content"):
        price = price_tag["content"].strip()
    else:
        match = re.search(r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]{1,2})?)"?', response.text)
        if match:
            price = match.group(1)
    if price and not price.startswith("$"):
        price = f"${price}"

    tier1 = {"title": title, "image_url": image_url,
             "description": description, "price": price}

    if not _thin(tier1):
        return tier1

    # Tier 2: structured data
    tier2 = _extract_tier2(soup, response.text)
    if tier2 and not _thin({"description": tier2.get("description")}):
        merged = {**tier1, **{k: v for k, v in tier2.items() if v}}
        if merged.get("price") and not merged["price"].startswith("$"):
            merged["price"] = f"${merged['price']}"
        if not merged.get("title"):
            merged["title"] = tier1["title"]
        return merged

    # Tier 3: headless render
    if playwright_enabled and PLAYWRIGHT_AVAILABLE:
        tier3 = _extract_tier3(url)
        if tier3 and not _thin({"description": tier3.get("description")}):
            merged = {**tier1, **{k: v for k, v in tier3.items() if v}}
            if merged.get("price") and not merged["price"].startswith("$"):
                merged["price"] = f"${merged['price']}"
            if not merged.get("title"):
                merged["title"] = tier1["title"]
            return merged

    # Tier 4: thin -> caller saves with manual fallback
    return tier1


# Backwards-compatible alias - autonomous_agent keeps calling this name.
extract_product_data = extract_product_data_tiered
