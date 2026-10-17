import os
import requests
from dotenv import load_dotenv

load_dotenv()

username = os.getenv("SUPABASE_USERNAME", "")
key = os.getenv("SUPABASE_ANON_KEY", "")

ref = username.split(".", 1)[1] if "." in username else username
rest = f"https://{ref}.supabase.co"

print("rest url:", rest)
print("key starts with:", key[:12] if key else "MISSING")

from database.repositories import CampaignRepository
camps = CampaignRepository().list_published_campaigns()
if not camps:
    print("No published campaigns found.")
else:
    r = requests.post(
        rest + "/rest/v1/page_events",
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={
            "campaign_id": str(camps[0]["id"]),
            "event_type": "view",
            "page_url": "http://terminal-probe",
        },
        timeout=15,
    )
    print("status:", r.status_code)
    print("body:", r.text[:200])