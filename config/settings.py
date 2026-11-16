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

SITE_BASE_URL = _get_setting("SITE_BASE_URL", "https://lovelyn.matchqip.com/")

# Only these verified campaigns may be auto-published or promoted in the initial launch.
INITIAL_LAUNCH_CAMPAIGN_IDS = frozenset({
    "b8d56c20-c801-4c97-ac8f-936bb5c36cba",
    "495a7cc2-6861-4818-b2c2-1729bf6955cc",
    "66d125ce-0523-492b-9679-3bd06d75e1be",
    "2b6fb996-c048-435b-82d8-9a64d196a1b8",
})

DEVTO_API_KEY = _get_setting("DEVTO_API_KEY")
BLUESKY_HANDLE = _get_setting("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = _get_setting("BLUESKY_APP_PASSWORD")
MEDIUM_API_KEY = _get_setting("MEDIUM_API_KEY")

# Optional LLM copy-polish. Unset = template copy exactly as before.
OPENAI_API_KEY = _get_setting("OPENAI_API_KEY")
COPY_AI_MODEL = _get_setting("COPY_AI_MODEL", "gpt-4o-mini")

PAYHIP_WEBHOOK_TOKEN = _get_setting("PAYHIP_WEBHOOK_TOKEN")

# Owned-product checkout URL (Payhip/Gumroad etc.). Unset = no Buy button.
OWNED_PRODUCT_URL = _get_setting("OWNED_PRODUCT_URL")

# Niche keyword for long-tail search headlines (e.g. "budget planner",
# "day trading journal", "declutter checklist"). Unset = generic buyer-intent.
SITE_NICHE_KEYWORD = _get_setting("SITE_NICHE_KEYWORD")

# Revenue targets (cents) - you set these based on your reality
AFFILIATE_WEEKLY_TARGET_CENTS = int(_get_setting("AFFILIATE_WEEKLY_TARGET_CENTS", "50000"))  # $500
OWNED_WEEKLY_TARGET_CENTS = int(_get_setting("OWNED_WEEKLY_TARGET_CENTS", "50000"))  # $500
COMBINED_MONTHLY_TARGET_CENTS = int(_get_setting("COMBINED_MONTHLY_TARGET_CENTS", "500000"))  # $5000

# Milestones
MILESTONE_THRESHOLDS_CENTS = [10000, 50000, 100000, 500000, 1000000]  # $100, $500, $1K, $5K, $10K