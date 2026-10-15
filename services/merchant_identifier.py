"""Identifies the merchant or marketplace from a URL."""

def identify_merchant(url: str) -> str:
    """Returns a normalized merchant name based on the domain."""
    url_lower = url.lower()
    
    if "etsy.com" in url_lower:
        return "Etsy"
    if "jvzoo.com" in url_lower:
        return "JVZoo"
    if "ebay.com" in url_lower:
        return "eBay"
    if "amazon.com" in url_lower or "amzn.to" in url_lower:
        return "Amazon"
    if "payhip.com" in url_lower:
        return "Payhip"
    if "printify.com" in url_lower or "printful.com" in url_lower:
        return "Print-on-Demand"
    if "shopify.com" in url_lower or "myshopify.com" in url_lower:
        return "Shopify"
        
    return "Independent / Other"