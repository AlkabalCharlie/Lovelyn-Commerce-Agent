"""Protects the application from Server-Side Request Forgery (SSRF)."""
import ipaddress
import socket
from urllib.parse import urlparse

from core.exceptions import SSRFError

def check_url_safety(url: str) -> str:
    """
    Validates a URL and ensures it does not point to private/internal networks.
    Returns the validated hostname if safe.
    """
    parsed = urlparse(url)
    
    if parsed.scheme not in ("http", "https"):
        raise SSRFError("Only http and https URLs are allowed.")
        
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("Invalid URL format.")

    # Block obvious internal names
    if hostname.lower() in ("localhost", "metadata.google.internal"):
        raise SSRFError("Access to internal networks is blocked.")

    try:
        # Resolve the domain to an IP address to check its true destination
        ip_string = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_string)
        
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise SSRFError("Access to internal or reserved IP addresses is blocked.")
            
        return hostname
    except socket.gaierror:
        raise SSRFError(f"Could not resolve domain name: {hostname}")