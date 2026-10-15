import streamlit as st

from database.connection import test_db_connection

st.set_page_config(
    page_title="Lovelyn | Commerce Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def overview_page() -> None:
    st.title("Lovelyn")
    st.markdown("### Cloud-Based Autonomous Commerce and Revenue Intelligence Platform")
    st.divider()

    st.header("Executive Overview")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Affiliate Net Commission Target",
            value="$50.00",
            help="Weekly target for verified, received affiliate commissions.",
        )
        st.info("Actual: $0.00 (Pending Phase 8 Integration)")

    with col2:
        st.metric(
            label="Owned-Product Net Profit Target",
            value="$50.00",
            help="Weekly target for net profit after all costs and fees.",
        )
        st.info("Actual: $0.00 (Pending Phase 8 Integration)")

    with col3:
        st.metric(
            label="Combined Weekly Target",
            value="$100.00",
            help="Total weekly financial goal.",
        )
        st.warning("Actual: $0.00 (Pending Phase 8 Integration)")

    st.divider()
    st.subheader("System Status")

    if test_db_connection():
        st.success("✅ Database Connected (Supabase)")
    else:
        st.error("❌ Database Connection Failed")


overview = st.Page(overview_page, title="Overview", icon="📊", default=True)
products = st.Page("pages/products.py", title="Products", icon="📦")

nav = st.navigation([overview, products])
nav.run()