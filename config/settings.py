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

# Full certificate verification is ON by default. It may be relaxed on a
# local machine only, never in the cloud.
SSL_VERIFY = _get_setting("LOVELYN_SSL_VERIFY", "true").lower() == "true"

if not (SUPABASE_USERNAME and SUPABASE_HOST and SUPABASE_PASSWORD):
    raise ValueError("Missing Supabase settings in .env file or Streamlit secrets.")