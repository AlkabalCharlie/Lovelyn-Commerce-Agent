import os

import requests
from dotenv import load_dotenv

load_dotenv()
ref = os.getenv("SUPABASE_USERNAME", "").split(".", 1)[-1]
token = os.getenv("GUMROAD_PING_TOKEN")
if not ref or not token:
    raise SystemExit("Set SUPABASE_USERNAME and GUMROAD_PING_TOKEN in .env first.")

url = f"https://{ref}.supabase.co/functions/v1/gumroad-ping?token={token}"

# Structured like a REAL Gumroad sale ping (form-encoded, cents, unsigned).
payload = {
    "seller_id": os.getenv("GUMROAD_SELLER_ID", "test-seller"),
    "product_id": "TEST-PRODUCT",
    "product_name": "Ping Test Game",
    "permalink": "pingtest",
    "sale_id": "PINGTEST-001",
    "price": "999",            # integer cents = $9.99
    "gumroad_fee": "47",
    "currency": "usd",
    "resource_name": "sale",
    "test": "false",
    "email": "buyer@example.com",
}
r = requests.post(url, data=payload, timeout=20)
print("SALE   :", r.status_code, r.text[:200])

# Replay (dedupe must no-op):
r2 = requests.post(url, data=payload, timeout=20)
print("REPLAY :", r2.status_code, r2.text[:200])

# Refund carries the SAME sale_id, different resource_name:
refund = dict(payload, resource_name="refund")
r3 = requests.post(url, data=refund, timeout=20)
print("REFUND :", r3.status_code, r3.text[:200])
