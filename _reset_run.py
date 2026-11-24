"""Reset today's buyer_intel_runs row when its run was INCOMPLETE (no needs
upserted). Complete, productive runs are never touched."""
from datetime import date
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import text
from database.connection import engine

with engine.begin() as c:
    n = c.execute(text(
        "DELETE FROM buyer_intel_runs WHERE run_date = :d "
        "AND needs_upserted = 0 AND products_matched = 0"),
        {"d": date.today()}).rowcount
print("removed incomplete run rows:", n)
