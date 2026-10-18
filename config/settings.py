import os

from dotenv import load_dotenv

load_dotenv()


def _get_setting(name: str, default: str = None) -> str:
    """Read a setting from environment variables, then Streamlit secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        secret = st.secrets.get(name)
        return secret if secret else default
    except Exception:
        return default


SUPABASE_USERNAME = _get_setting("SUPABASE_USERNAME")
SUPABASE_HOST = _get_setting("SUPABASE_HOST")
SUPABASE_PASSWORD = _get_setting("SUPABASE_PASSWORD")
SUPABASE_ANON_KEY = _get_setting("SUPABASE_ANON_KEY")
APP_PASSWORD = _get_setting("APP_PASSWORD")

SSL_VERIFY = str(_get_setting("LOVELYN_SSL_VERIFY", "true")).lower() == "true"

# Owner throttle: "full" = agent approves and publishes on its own (default).
# Set to "gated" any time to make new campaigns wait as drafts.
AGENT_AUTONOMY = _get_setting("AGENT_AUTONOMY", "full").lower()

SITE_BASE_URL = _get_setting(
    "SITE_BASE_URL", "https://alkabalcharlie.github.io/Lovelyn-Commerce-Agent/"
)