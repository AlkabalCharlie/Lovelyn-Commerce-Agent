import os

import requests
from dotenv import load_dotenv

load_dotenv()

ref = os.getenv("SUPABASE_USERNAME").split(".", 1)[1]
token = os.getenv("PAYHIP_WEBHOOK_TOKEN")
url = f"https://{ref}.supabase.co/functions/v1/payhip-sales?token={token}"

payload = {
    "event": "paid",
    "order_id": "TEST-ORDER-1",
    "amount": 7,
    "currency": "USD",
    "product_name": "Webhook Test",
}
r = requests.post(url, json=payload, timeout=20)
print("status:", r.status_code)
print("body:", r.text[:200])