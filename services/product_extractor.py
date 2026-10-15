"""Extracts basic product information from a web page."""
import requests
from bs4 import BeautifulSoup

from core.exceptions import ExtractionError
from services.url_safety import check_url_safety

def extract_product_data(url: str) -> dict:
    """Fetches a URL safely and extracts the title and main image."""
    # 1. Security check first
    check_url_safety(url)
    
    # 2. Fetch the page
    headers = {
        "User-Agent": "LovelynBot/1.0 (Commerce Intelligence Agent)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ExtractionError(f"Network error while fetching URL: {e}")

    # 3. Parse HTML
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Extract Title (Try OpenGraph first, then standard HTML title)
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()
        
    # Extract Image (Try OpenGraph image)
    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image["content"].strip()
        
    if not title:
        title = "Extracted Product (No title found)"
        
    return {
        "title": title,
        "image_url": image_url
    }