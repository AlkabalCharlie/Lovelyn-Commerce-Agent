"""End-to-end proof: link -> click -> sale -> auto-logged revenue -> optimizer verdict.

Simulates one human journey plus one sale, verifies every link in the chain,
then cleans up so the ledger stays honest. Run: python prove_loop.py
"""
import os

import requests
from dotenv import load_dotenv
from sqlalchemy import text

from database.connection import engine
from database.repositories import CampaignRepository
from services.optimizer import decide_action

load_dotenv()

REF = os.getenv("SUPABASE_USERNAME").split(".", 1)[1]
ANON = os.getenv("SUPABASE_ANON_KEY")
TOKEN = os.getenv("PAYHIP_WEBHOOK_TOKEN")
BASE = f"https://{REF}.supabase.co"
PROOF_URL = "e2e-proof"

RECOMPUTE_SQL = """
UPDATE campaigns c SET revenue_cents = COALESCE((
    SELECT SUM(f.amount_cents)
    FROM financial_events f
    JOIN products p ON p.url ILIKE '%' || f.source || '%'
    WHERE p.id = c.product_id AND f.stream = 'owned'
), 0)
"""


def event_headers():
    return {
        "apikey": ANON,
        "Authorization": f"Bearer {ANON}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def main():
    repo = CampaignRepository()
    stats = [r for r in repo.get_traffic_stats() if r["status"] == "published"]
    if not stats:
        print("No unflagged published campaign to prove with; aborting cleanly.")
        return
    row = stats[0]
    cid = str(row["id"])
    order_id = f"E2E-{cid[:8]}"

    r1 = requests.post(f"{BASE}/rest/v1/page_events", headers=event_headers(),
                       json={"campaign_id": cid, "event_type": "view", "page_url": PROOF_URL}, timeout=15)
    print(f"[1/5] view beacon ........ {r1.status_code}")

    r2 = requests.post(f"{BASE}/rest/v1/page_events", headers=event_headers(),
                       json={"campaign_id": cid, "event_type": "click", "page_url": PROOF_URL}, timeout=15)
    print(f"[2/5] click beacon ....... {r2.status_code}")

    r3 = requests.post(f"{BASE}/functions/v1/payhip-sales?token={TOKEN}",
                       json={"event": "paid", "order_id": order_id, "amount": 7, "currency": "USD",
                             "product_name": "End-to-end proof"}, timeout=20)
    print(f"[3/5] sale webhook ....... {r3.status_code} {r3.text[:80]}")

    with engine.connect() as connection:
        found = connection.execute(text("SELECT amount_cents FROM financial_events WHERE external_id = :oid"), {"oid": order_id}).fetchone()
    cents = int(found[0]) if found else 0
    print(f"[4/5] ledger auto-row .... {'found ' + str(cents) + ' cents' if found else 'MISSING'}")

    fresh = [r for r in repo.get_traffic_stats() if str(r["id"]) == cid][0]
    verdict = decide_action(fresh["views"], fresh["clicks"], 0, None, cents)
    print(f"[5/5] optimizer verdict .. {verdict} (revenue {cents} cents)")

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM page_events WHERE page_url = :u"), {"u": PROOF_URL})
        connection.execute(text("DELETE FROM financial_events WHERE external_id LIKE 'E2E-%'"))
        connection.execute(text(RECOMPUTE_SQL))
    print("CLEANUP: test events removed, revenue resynced to ledger truth.")

    ok = r1.status_code == 201 and r2.status_code == 201 and r3.status_code == 200 and found and verdict == "winner"
    print("END-TO-END PROOF:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()