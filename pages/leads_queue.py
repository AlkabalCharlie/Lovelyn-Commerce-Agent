"""Leads + Publishing Queue: owner-only dashboard pages.

Reached via the EXISTING password gate (require_login runs in app.py before
navigation; every pages/* module inherits that gate — Streamlit's st.Page
navigation only renders after `if not require_login(): st.stop()`).
No public endpoint is created. Read-only: owners review; nothing auto-posts.
"""
import json

import streamlit as st

from database.connection import engine
from database.connection import engine
from database.repositories import CampaignRepository, LeadRepository
from services.publishing_queue import ensure_shorts_columns

st.title("Leads & Publishing Queue")
st.caption("Buyer-intent opportunities (read-only — Reddit stays reply-by-hand) "
           "and owner-publishing packages for channels without credentials.")

tab1, tab2 = st.tabs(["Qualified Leads", "Publishing Queue"])

try:
    ensure_shorts_columns()  # additive; makes shorts states visible pre-migration
except Exception:
    pass

with tab1:
    leads = LeadRepository().list_leads()
    if not leads:
        st.info("No leads yet. The scout stores only buyer-intent-scored, "
                "qualified opportunities (weak posts are rejected at insert).")
    for lead in leads:
        with st.expander(f"[{lead['subreddit'] or 'n/a'}] {lead['title']}"):
            st.markdown(f"**URL:** {lead['url']}")
            st.markdown(f"**Status:** {lead['status']} · "
                        f"**Found:** {lead['found_at']}")
            st.markdown(f"**Demand score provenance:** {lead['notes'] or '—'}")
            st.markdown(f"**Matched product:** {lead.get('product_name') or '—'}")

with tab2:
    repo = CampaignRepository()
    with engine.connect() as conn:  # read-only queue listing
        from sqlalchemy import text
        rows = conn.execute(text(
            "SELECT q.id, q.channel, q.title, q.format, q.status, "
            "q.publication_url, q.package, q.campaign_id, q.video_path, "
            "q.youtube_video_id, q.error_detail, q.generated_at, "
            "c.headline AS campaign_headline "
            "FROM publishing_queue q LEFT JOIN campaigns c ON c.id = q.campaign_id "
            "ORDER BY q.created_at DESC")).mappings().all()
    if not rows:
        st.info("Queue is empty.")
    for row in rows:
        pkg = row["package"]
        if isinstance(pkg, str):
            pkg = json.loads(pkg)
        origin = pkg.get("origin", "unspecified")
        opp = pkg.get("opportunity")
        label = f"[{row['channel']}] {row['title']}"
        with st.expander(label):
            st.markdown(f"**Status:** `{row['status']}` · **Origin:** `{origin}` "
                        f"· **Campaign:** {row.get('campaign_headline') or '—'}")
            # Shorts pipeline visibility: distinct states, never conflated.
            if row.get("youtube_video_id") and row["publication_url"]:
                st.success(f"🎥 **Published on YouTube:** {row['publication_url']}")
            elif row.get("video_path"):
                st.info(f"🎬 **Video rendered** (`{row['video_path']}`) — "
                        f"awaiting upload (credentials or visibility setting).")
            if row.get("error_detail"):
                st.error(f"**Needs attention:** {row['error_detail']}")
            if row["publication_url"] and not row.get("youtube_video_id"):
                st.markdown(f"**Published at:** {row['publication_url']}")
            elif not row["publication_url"] and not row.get("video_path"):
                st.warning("Queued — NOT published. Publish manually, then "
                           "record the URL here.")
            if opp:
                st.markdown(f"**Opportunity:** [{opp.get('title')}]({opp.get('source_url')}) "
                            f"· score {opp.get('score')}")
            st.markdown("**Package:**")
            st.json(pkg)
