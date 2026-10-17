"""Standalone trigger to rebuild the public traffic site."""
from dotenv import load_dotenv

load_dotenv()

from services.site_builder import build_site

count = build_site()
print(f"Traffic site rebuilt with {count} campaign page(s) in docs/.")