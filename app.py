from datetime import date, timedelta

import streamlit as st

from core.security import require_login, render_sign_out
from database.connection import test_db_connection
from database.repositories import FinanceRepository
from models.finance import format_cents
from config.settings import (
    AFFILIATE_WEEKLY_TARGET_CENTS,
    OWNED_WEEKLY_TARGET_CENTS,
    COMBINED_MONTHLY_TARGET_CENTS,
)

st.set_page_config(page_title="Lovelyn | Commerce Intelligence", page_icon="📊", layout="wide", initial_sidebar_state="expanded")


def overview_page() -> None:
    st.title("Lovelyn")
    st.markdown("### Cloud-Based Autonomous Commerce and Revenue Intelligence Platform")
    st.divider()

    st.header("Executive Overview")
    fin = FinanceRepository()
    week_ago = date.today() - timedelta(days=7)
    totals = fin.sum_by_stream_since(week_ago)
    aff = totals.get("affiliate", 0)
    own = totals.get("owned", 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Affiliate Received (7 days)", format_cents(aff), help="Verified received commissions, last 7 days.")
        st.caption(f"Target: {format_cents(AFFILIATE_WEEKLY_TARGET_CENTS)} / week")
    with col2:
        st.metric("Owned Received (7 days)", format_cents(own), help="Verified received profit, last 7 days.")
        st.caption(f"Target: {format_cents(OWNED_WEEKLY_TARGET_CENTS)} / week")
    with col3:
        st.metric("Combined Received (7 days)", format_cents(aff + own), help="Total verified received money, last 7 days.")
        st.caption(f"Target: {format_cents(COMBINED_MONTHLY_TARGET_CENTS)} / month")

    st.divider()
    st.subheader("System Status")
    if test_db_connection():
        st.success("✅ Database Connected (Supabase)")
    else:
        st.error("❌ Database Connection Failed")


if not require_login():
    st.stop()

render_sign_out()

overview = st.Page(overview_page, title="Overview", icon="📊", default=True)
products = st.Page("pages/products.py", title="Products", icon="📦")
campaigns = st.Page("pages/campaigns.py", title="Campaigns", icon="📢")
traffic = st.Page("pages/traffic.py", title="Traffic", icon="📈")
finance = st.Page("pages/finance.py", title="Finance", icon="💰")
agent_logs = st.Page("pages/agent_logs.py", title="Agent Logs", icon="🤖")

nav = st.navigation([overview, products, campaigns, traffic, finance, agent_logs])
nav.run()