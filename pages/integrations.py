"""Integrations page: persisted health of every external dependency."""
import streamlit as st

from database.repositories import IntegrationHealthRepository

st.title("Integrations")
st.caption("Live status of every external channel and webhook. A row saying "
           "'configuration_missing' means that channel is earning nothing until "
           "you configure it - failures are never hidden.")

repo = IntegrationHealthRepository()

_LABELS = {
    "connected": ("🟢 Connected", "success"),
    "authorization_expired": ("🟠 Authorization expired", "warning"),
    "configuration_missing": ("⚪ Configuration missing", "warning"),
    "quota_exceeded": ("🟠 API quota exceeded", "warning"),
    "failed": ("🔴 Failed", "error"),
    "awaiting_verification": ("🟡 Awaiting verification", "warning"),
}

try:
    rows = repo.list_status()
except Exception as exc:
    rows = []
    st.warning("Integration health needs the Phase 2 migration "
               "(database/migrations/phase2_attribution.sql) - run it in Supabase first.")
    print(f"Health load failed: {exc}")

if not rows:
    st.info("No integration status recorded yet. The daily agent writes a row "
            "for every channel on each run.")
else:
    for row in rows:
        label, kind = _LABELS.get(row["status"], (row["status"], "warning"))
        with st.container(border=True):
            st.markdown(f"**{row['integration']}** — {label}")
            if row["detail"]:
                st.caption(row["detail"])
            st.caption(f"checked: {row['checked_at']}")
