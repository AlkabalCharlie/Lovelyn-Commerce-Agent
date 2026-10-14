import streamlit as st

# Configure the browser tab title and layout
st.set_page_config(
    page_title="Lovelyn | Commerce Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    # Header
    st.title("Lovelyn")
    st.markdown("### Cloud-Based Autonomous Commerce and Revenue Intelligence Platform")
    st.divider()

    # Sidebar Navigation (Placeholder for Phase 2+)
    st.sidebar.title("Navigation")
    st.sidebar.markdown("### Status: Phase 1 - Foundation")
    
    # Main Dashboard Content
    st.header("Executive Overview")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="Affiliate Net Commission Target",
            value="$50.00",
            help="Weekly target for verified, received affiliate commissions."
        )
        st.info("Actual: $0.00 (Pending Phase 8 Integration)")

    with col2:
        st.metric(
            label="Owned-Product Net Profit Target",
            value="$50.00",
            help="Weekly target for net profit after all costs and fees."
        )
        st.info("Actual: $0.00 (Pending Phase 8 Integration)")

    with col3:
        st.metric(
            label="Combined Weekly Target",
            value="$100.00",
            help="Total weekly financial goal."
        )
        st.warning("Actual: $0.00 (Pending Phase 8 Integration)")

    st.divider()
    
    st.subheader("System Status")
    st.success("✅ Application is running successfully in the cloud.")
    st.info("ℹ️ Next Step: Connect persistent database (Supabase) in Phase 2.")

if __name__ == "__main__":
    main()