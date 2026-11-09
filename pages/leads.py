"""Leads page: live Reddit buyer questions surfaced by the Scout.

The bot NEVER posts to Reddit. You reply by hand in your own browser -
open the link, answer as yourself, then mark the lead Contacted or Skipped.
"""
from datetime import datetime, timezone

import streamlit as st

from database.repositories import VALID_LEAD_STATUSES, LeadRepository

st.title("Leads")
st.caption("Live Reddit questions the scout found. YOU reply by hand in your browser - "
           "the bot never posts or comments on Reddit.")

repo = LeadRepository()

status_filter = st.selectbox("Filter", ["all", "new", "contacted", "skipped"])
leads = repo.list_leads(status=status_filter)

if not leads:
    st.info("No leads yet. The scout runs with the daily grind and caps at 10 new leads per run.")
    st.stop()

counts = {s: 0 for s in VALID_LEAD_STATUSES}
for row in repo.list_leads(status="all", limit=500):
    counts[row["status"]] = counts.get(row["status"], 0) + 1

c1, c2, c3 = st.columns(3)
c1.metric("New", counts["new"])
c2.metric("Contacted", counts["contacted"])
c3.metric("Skipped", counts["skipped"])

st.divider()

for row in leads:
    age_hours = max(0, (datetime.now(timezone.utc) - row["found_at"]).total_seconds() / 3600)
    with st.container(border=True):
        st.markdown(f"**{row['title']}**")
        st.caption(f"r/{row['subreddit']} | {age_hours:.0f}h old | Status: {row['status']}"
                   + (f" | Product: {row['product_name']}" if row["product_name"] else ""))
        st.markdown(f"[Open on Reddit]({row['url']})")
        if row["notes"]:
            st.write(row["notes"])
        b1, b2 = st.columns(2)
        if b1.button("Mark contacted", key=f"contacted-{row['id']}"):
            repo.update_status(row["id"], "contacted")
            st.rerun()
        if b2.button("Skip", key=f"skip-{row['id']}"):
            repo.update_status(row["id"], "skipped")
            st.rerun()
