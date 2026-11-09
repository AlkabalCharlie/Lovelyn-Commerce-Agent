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
AGENT_AUTONOMY = _get_setting("AGENT_AUTONOMY", "full").lower()

SITE_BASE_URL = _get_setting(
    "SITE_BASE_URL", "https://alkabalcharlie.github.io/Lovelyn-Commerce-Agent/"
)

DEVTO_API_KEY = _get_setting("DEVTO_API_KEY")
BLUESKY_HANDLE = _get_setting("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = _get_setting("BLUESKY_APP_PASSWORD")
MEDIUM_API_KEY = _get_setting("MEDIUM_API_KEY")

PAYHIP_WEBHOOK_TOKEN = _get_setting("PAYHIP_WEBHOOK_TOKEN")

# Revenue targets (cents) - you set these based on your reality
AFFILIATE_WEEKLY_TARGET_CENTS = int(_get_setting("AFFILIATE_WEEKLY_TARGET_CENTS", "50000"))  # $500
OWNED_WEEKLY_TARGET_CENTS = int(_get_setting("OWNED_WEEKLY_TARGET_CENTS", "50000"))  # $500
COMBINED_MONTHLY_TARGET_CENTS = int(_get_setting("COMBINED_MONTHLY_TARGET_CENTS", "500000"))  # $5000

# Milestones
MILESTONE_THRESHOLDS_CENTS = [10000, 50000, 100000, 500000, 1000000]  # $100, $500, $1K, $5K, $10K