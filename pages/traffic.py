"""Traffic page: real views and clicks from the public campaign pages."""
import streamlit as st

from database.repositories import CampaignRepository

st.title("Traffic")
st.caption("Real human views and clicks recorded by the beacon on your live campaign pages.")

repo = CampaignRepository()
stats = repo.get_traffic_stats()

if not stats:
    st.info("No campaigns yet.")
    st.stop()

total_views = sum(row["views"] for row in stats)
total_clicks = sum(row["clicks"] for row in stats)

c1, c2, c3 = st.columns(3)
c1.metric("Total page views", total_views)
c2.metric("Total CTA clicks", total_clicks)
c3.metric("Click-through rate", f"{(total_clicks / total_views * 100):.1f}%" if total_views else "0.0%")

st.divider()
for row in stats:
    ctr = f"{(row['clicks'] / row['views'] * 100):.1f}%" if row["views"] else "0.0%"
    with st.container(border=True):
        st.markdown(f"**{row['headline']}**")
        st.caption(f"Status: {row['status']} | Views: {row['views']} | Clicks: {row['clicks']} | CTR: {ctr}")