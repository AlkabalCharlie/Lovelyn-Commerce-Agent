"""Read-only verification of the buyer_intelligence v2 migration in Supabase.

Confirms: columns exist with the right types/defaults, CHECK constraint
allows exactly the four classifications, and the classification index
exists. No data modification.
"""
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import text
from database.connection import engine

EXPECTED_COLUMNS = {
    "classification": ("text", "'weak_match'::text"),
    "gate_explanation": ("text", None),
    "gate_reasons": ("jsonb", "'{}'::jsonb"),
}

with engine.connect() as c:
    cols = c.execute(text(
        "SELECT column_name, data_type, column_default, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_name = 'buyer_product_matches'")).mappings().all()
    print("== COLUMNS ==")
    names = set()
    for r in cols:
        names.add(r["column_name"])
        if r["column_name"] in EXPECTED_COLUMNS:
            exp_type, exp_default = EXPECTED_COLUMNS[r["column_name"]]
            type_ok = r["data_type"] == exp_type
            default_ok = (exp_default is None or
                          (r["column_default"] or "").startswith(exp_default))
            print(f"  {r['column_name']}: type={r['data_type']} "
                  f"({'OK' if type_ok else 'MISMATCH'}) "
                  f"default={r['column_default']} "
                  f"({'OK' if default_ok else 'MISMATCH'})")
    for col in EXPECTED_COLUMNS:
        print(f"  present: {col}: {col in names}")

    print("== CHECK CONSTRAINT ==")
    checks = c.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) AS def "
        "FROM pg_constraint WHERE conrelid = 'buyer_product_matches'::regclass "
        "AND contype = 'c'")).mappings().all()
    for r in checks:
        print(f"  {r['conname']}: {r['def'][:160]}")

    print("== INDEX ==")
    idx = c.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE tablename = 'buyer_product_matches'")).mappings().all()
    for r in idx:
        print(f"  {r['indexname']}")
    has_idx = any("idx_buyer_matches_classification" == r["indexname"]
                  for r in idx)
    print(f"  idx_buyer_matches_classification present: {has_idx}")

    print("== EXISTING ROW COUNTS (read-only) ==")
    print("  buyer_product_matches:",
          c.execute(text("SELECT count(*) FROM buyer_product_matches")).scalar())
    print("  buyer_needs:",
          c.execute(text("SELECT count(*) FROM buyer_needs")).scalar())
