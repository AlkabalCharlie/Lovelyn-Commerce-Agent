"""Extracts product information from a web page, respecting refusals."""
import re

import requests
from bs4 import BeautifulSoup

from core.exceptions import ExtractionError
from services.url_safety import check_url_safety


def extract_product_data(url: str) -> dict:
    """Fetches a URL safely and extracts title, image, description, and price."""
    check_url_safety(url)

    headers = {"User-Agent": "LovelynBot/1.0 (Commerce Intelligence Agent)"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ExtractionError(f"Network error while fetching URL: {e}")

    soup = BeautifulSoup(response.text, "html.parser")

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

    if not title:
        title = "Extracted Product (No title found)"

    return {"title": title, "image_url": image_url, "description": description, "price": price}