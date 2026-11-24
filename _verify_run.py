"""Post-run DB verification (read-only): what the pipeline actually stored,
by classification, and whether recommendations obey the gate."""
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import text
from database.connection import engine

with engine.connect() as c:
    print("== RUN LEDGER ==")
    run = c.execute(text("SELECT * FROM buyer_intel_runs")).mappings().first()
    if run:
        for k in ("run_date", "finished_at", "evidence_collected",
                  "needs_upserted", "products_matched",
                  "unmet_opportunities", "report_error"):
            print(f"  {k}: {run.get(k)}")
        print(f"  sources_ok: {run.get('sources_ok')}")
        print(f"  sources_failed: {run.get('sources_failed')}")
        print(f"  email_sent_at: {run.get('report_email_sent_at')}")

    print("== EVIDENCE BY AIDA STAGE ==")
    for r in c.execute(text(
            "SELECT aida_stage, count(*) n FROM buyer_evidence "
            "GROUP BY aida_stage ORDER BY n DESC")).mappings().all():
        print(f"  {r['aida_stage']}: {r['n']}")
    print("  total:",
          c.execute(text("SELECT count(*) FROM buyer_evidence")).scalar())

    print("== NEEDS ==")
    needs = c.execute(text(
        "SELECT count(*) FROM buyer_needs")).scalar()
    print("  total needs:", needs)

    print("== MATCHES BY CLASSIFICATION ==")
    for r in c.execute(text(
            "SELECT classification, count(*) n FROM buyer_product_matches "
            "GROUP BY classification")).mappings().all():
        print(f"  {r['classification']}: {r['n']}")
    total = c.execute(text(
        "SELECT count(*) FROM buyer_product_matches")).scalar()
    print("  total matches:", total)

    print("== GATE FIELDS POPULATED? ==")
    filled = c.execute(text(
        "SELECT count(*) FROM buyer_product_matches "
        "WHERE gate_explanation IS NOT NULL "
        "AND gate_reasons != '{}'::jsonb")).scalar()
    print(f"  matches with gate_explanation+gate_reasons: {filled}/{total}")

    print("== UNMET NEEDS (no direct match) ==")
    unmet = c.execute(text(
        "SELECT n.title, n.intent_score, n.aida_stage, n.confidence "
        "FROM buyer_needs n WHERE NOT EXISTS ("
        "  SELECT 1 FROM buyer_product_matches m "
        "  WHERE m.need_id = n.id AND m.classification = 'direct_match') "
        "ORDER BY n.intent_score DESC LIMIT 5")).mappings().all()
    for r in unmet:
        print(f"  [{r['intent_score']}/100 {r['aida_stage']} "
              f"{r['confidence']}] {r['title'][:80]}")
    print("  unmet count:", len(unmet))

    print("== TOP DIRECT MATCHES (recommended set) ==")
    for r in c.execute(text(
            "SELECT m.classification, m.match_score, m.product_name, "
            "n.title FROM buyer_product_matches m "
            "JOIN buyer_needs n ON n.id = m.need_id "
            "WHERE m.classification = 'direct_match' "
            "ORDER BY m.match_score DESC LIMIT 5")).mappings().all():
        print(f"  [{r['match_score']}] {r['product_name']} <- "
              f"{r['title'][:60]}")

    print("== SAMPLE GATE REASON (one direct match) ==")
    row = c.execute(text(
        "SELECT classification, gate_explanation, gate_reasons "
        "FROM buyer_product_matches WHERE classification = 'direct_match' "
        "LIMIT 1")).mappings().first()
    if row:
        print("  classification:", row["classification"])
        print("  explanation:", (row["gate_explanation"] or "")[:180])
