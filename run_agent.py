"""Standalone script to trigger the autonomous agent from the command line or cron."""
import sys
from dotenv import load_dotenv

# Ensure environment variables are loaded before anything else
load_dotenv()

try:
    from services.autonomous_agent import run_daily_grind
    result = run_daily_grind()
    print(f"Agent finished: {result}")
except Exception as e:
    print(f"Agent crashed: {e}")
    sys.exit(1)