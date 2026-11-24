"""Verify match-insert round-trip with classification + gate fields, then
clean up the test rows. Does not touch real research data."""
from database.buyer_repositories import (
    BuyerNeedsRepository,
    BuyerProductMatchRepository,
)
from database.connection import engine
from sqlalchemy import text

r = BuyerNeedsRepository()
nid = r.upsert(cluster_key="test-verify-xyz", title="T",
               problem_description="D", target_audience="A",
               aida_stage="interest", intent_score=50, score_reasoning="r",
               observed=["x"], inferred=["y"], evidence_count=2,
               source_urls=["http://u"])
print("need upsert ok:", bool(nid))

m = BuyerProductMatchRepository()
ok = m.insert(need_id=nid, product_url="http://p", product_name="P",
              match_score=70, match_reasoning="m",
              classification="partial_match", gate_explanation="ge",
              gate_reasons={"problem_alignment": "pass"})
print("match insert ok:", ok)

row = engine.connect().execute(text(
    "SELECT classification, gate_explanation, gate_reasons "
    "FROM buyer_product_matches WHERE need_id = :n"),
    {"n": nid}).mappings().first()
print("round-trip:", dict(row))

with engine.begin() as c:
    c.execute(text("DELETE FROM buyer_product_matches WHERE need_id = :n"),
              {"n": nid})
    c.execute(text("DELETE FROM buyer_needs WHERE cluster_key = 'test-verify-xyz'"))
print("test rows cleaned")
