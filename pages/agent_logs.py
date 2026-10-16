"""Agent Logs page: View the autonomous heartbeat's daily activity."""
import streamlit as st
from database.repositories import AgentLogRepository

st.title("🤖 Autonomous Agent Logs")
st.caption("The daily grind. This log shows what the background agent did automatically while you were away.")

log_repo = AgentLogRepository()

if st.button("Run Agent Manually Now", type="primary"):
    with st.spinner("Executing daily grind..."):
        from services.autonomous_agent import run_daily_grind
        result = run_daily_grind()
        st.success(result)
        st.rerun()

st.divider()
st.subheader("Recent Activity")

logs = log_repo.get_recent_logs(limit=50)

if not logs:
    st.info("The agent hasn't run yet. Click the button above to trigger it manually!")
else:
    for log in logs:
        action = log['action_type']
        details = log['details']
        timestamp = log['created_at'].strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if action == "START":
            st.markdown(f"🟢 **[{timestamp}] START:** {details}")
        elif action == "COMPLETE":
            st.markdown(f"🏁 **[{timestamp}] COMPLETE:** {details}")
        elif action == "GENERATE":
            st.markdown(f"🧠 **[{timestamp}] GENERATE:** {details}")
        elif action == "APPROVE":
            st.markdown(f"✅ **[{timestamp}] APPROVE:** {details}")
        elif action == "PUBLISH":
            st.markdown(f"🚀 **[{timestamp}] PUBLISH:** {details}")
        else:
            st.markdown(f"⚪ **[{timestamp}] {action}:** {details}")