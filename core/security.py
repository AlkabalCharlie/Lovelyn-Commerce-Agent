"""Authentication gate for the Lovelyn dashboard."""
from secrets import compare_digest

import streamlit as st

from config.settings import APP_PASSWORD

SESSION_KEY = "lovelyn_authenticated"


def verify_password(candidate: str, expected: str) -> bool:
    """Constant-time comparison of the entered password."""
    if not isinstance(candidate, str) or not isinstance(expected, str):
        return False
    return compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def require_login() -> bool:
    """Return True only when the current session is authenticated."""
    if not APP_PASSWORD:
        st.error(
            "Security stop: APP_PASSWORD is not configured. "
            "Set it in .env (local) or Streamlit Secrets (cloud)."
        )
        return False
    if st.session_state.get(SESSION_KEY):
        return True

    st.title("Sign in to Lovelyn")
    st.caption("This dashboard contains private business and financial records.")
    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if verify_password(password, APP_PASSWORD):
            st.session_state[SESSION_KEY] = True
            st.rerun()
        st.error("Incorrect password.")
    return False


def render_sign_out() -> None:
    """Sidebar button that ends the session."""
    if st.sidebar.button("Sign out"):
        st.session_state.pop(SESSION_KEY, None)
        st.rerun()