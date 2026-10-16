import streamlit as st
from core.security import require_login, render_sign_out
from database.connection import test_db_connection

st.set_page_config(page_title="Lovelyn | Commerce Intelligence", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

def overview_page() -> None:
    st.title("Lovelyn")
    st.markdown("### Cloud-Based Autonomous Commerce and Revenue Intelligence Platform")
    st.divider()
    st.header("Executive Overview")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Affiliate Target", "$50.00"); st.info("Actual: $0.00")
    with col2: st.metric("Owned Target", "$50.00"); st.info("Actual: $0.00")
    with col3: st.metric("Combined Target", "$100.00"); st.warning("Actual: $0.00")
    st.divider()
    st.subheader("System Status")
    if test_db_connection(): st.success("✅ Database Connected (Supabase)")
    else: st.error("❌ Database Connection Failed")

if not require_login():
    st.stop()

render_sign_out()

overview = st.Page(overview_page, title="Overview", icon="📊", default=True)
products = st.Page("pages/products.py", title="Products", icon="📦")
campaigns = st.Page("pages/campaigns.py", title="Campaigns", icon="📢")
agent_logs = st.Page("pages/agent_logs.py", title="Agent Logs", icon="🤖")

nav = st.navigation([overview, products, campaigns, agent_logs])
nav.run()