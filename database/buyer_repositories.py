"""Persistence for the buyer-intelligence engine.

All SQL for buyer_evidence, buyer_needs, buyer_product_matches and
buyer_intel_runs lives here (same rule as repositories.py: ALL SQL in the
repository layer). Every insert path dedupes:
  - evidence via dedupe_key (content address)  -> repeat runs are no-ops
  - needs via cluster_key                      -> upsert, history preserved
  - matches via (need_id, product_url)         -> no duplicate candidates
  - daily report via report_email_sent_at      -> one email per day, ever
"""
import uuid
from datetime import date

from sqlalchemy import text

from database.connection import engine
from services.buyer_intent import confidence_for


class BuyerEvidenceRepository:
    def insert(self, *, dedupe_key: str, source: str, source_url: str,
               title: str, author: str = None, body: str = None,
               context: str = None, published_at=None,
               aida_stage: str = "none", raw_scores=None) -> bool:
        """Insert one evidence row. Returns True only when NEW (dedupe by
        dedupe_key means repeated runs and re-reads never duplicate)."""
        with engine.begin() as connection:
            result = connection.execute(text(
                "INSERT INTO buyer_evidence (dedupe_key, source, source_url, "
                "author, title, body, context, published_at, aida_stage, raw_scores) "
                "VALUES (:k, :s, :u, :a, :t, :b, :c, "
                "COALESCE(:p::timestamptz, now()), :stage, "
                "COALESCE(:raw::jsonb, '{}'::jsonb)) "
                "ON CONFLICT (dedupe_key) DO NOTHING RETURNING id"),
                {"k": dedupe_key, "s": source, "u": source_url, "a": author,
                 "t": title, "b": body, "c": context, "p": published_at,
                 "stage": aida_stage,
                 "raw": __import__("json").dumps(raw_scores or {})})
            return result.first() is not None

    def count_by_stage(self, run_date: date) -> dict:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT aida_stage, count(*) AS n FROM buyer_evidence "
                "WHERE retrieved_at::date = :d GROUP BY aida_stage"),
                {"d": run_date}).mappings().all()
        return {r["aida_stage"]: r["n"] for r in rows}


class BuyerNeedsRepository:
    def upsert(self, *, cluster_key: str, title: str, problem_description: str,
               target_audience: str, aida_stage: str, intent_score: int,
               score_reasoning: str, observed: list, inferred: list,
               evidence_count: int, source_urls: list,
               latest_evidence_at=None, desired_features: list = None,
               price_sensitivity: str = None, common_objections: list = None,
               unmet_aspects: list = None, suggested_categories: list = None) -> str:
        """Upsert a buyer-need cluster. last_updated advances only through
        real runs; first_seen is immutable so demand-growth is measurable.
        Returns the row id."""
        need_id = str(uuid.uuid4())
        confidence = confidence_for(evidence_count, intent_score)
        import json
        with engine.begin() as connection:
            row = connection.execute(text(
                "INSERT INTO buyer_needs (id, cluster_key, title, "
                "problem_description, target_audience, aida_stage, "
                "intent_score, score_reasoning, observed_vs_inferred, "
                "confidence, evidence_count, source_urls, latest_evidence_at, "
                "desired_features, price_sensitivity, common_objections, "
                "unmet_aspects, suggested_categories) "
                "VALUES (:id, :ck, :t, :pd, :ta, :st, :sc, :sr, :ovi::jsonb, "
                ":cf, :ec, :su::jsonb, COALESCE(:le::timestamptz, now()), "
                ":df::jsonb, :ps, :co::jsonb, :um::jsonb, :sgc::jsonb) "
                "ON CONFLICT (cluster_key) DO UPDATE SET "
                "title = EXCLUDED.title, "
                "problem_description = EXCLUDED.problem_description, "
                "target_audience = EXCLUDED.target_audience, "
                "aida_stage = EXCLUDED.aida_stage, "
                "intent_score = EXCLUDED.intent_score, "
                "score_reasoning = EXCLUDED.score_reasoning, "
                "observed_vs_inferred = EXCLUDED.observed_vs_inferred, "
                "confidence = EXCLUDED.confidence, "
                "evidence_count = EXCLUDED.evidence_count, "
                "source_urls = EXCLUDED.source_urls, "
                "latest_evidence_at = EXCLUDED.latest_evidence_at, "
                "desired_features = EXCLUDED.desired_features, "
                "price_sensitivity = EXCLUDED.price_sensitivity, "
                "common_objections = EXCLUDED.common_objections, "
                "unmet_aspects = EXCLUDED.unmet_aspects, "
                "suggested_categories = EXCLUDED.suggested_categories, "
                "last_updated = current_date "
                "RETURNING id"),
                {"id": need_id, "ck": cluster_key, "t": title, "pd": problem_description,
                 "ta": target_audience, "st": aida_stage, "sc": intent_score,
                 "sr": score_reasoning,
                 "ovi": json.dumps({"observed": observed, "inferred": inferred}),
                 "cf": confidence, "ec": evidence_count,
                 "su": json.dumps(source_urls), "le": latest_evidence_at,
                 "df": json.dumps(desired_features or []),
                 "ps": price_sensitivity,
                 "co": json.dumps(common_objections or []),
                 "um": json.dumps(unmet_aspects or []),
                 "sgc": json.dumps(suggested_categories or [])}).first()
            return str(row[0]) if row else None

    def top_needs(self, limit: int = 10, min_score: int = 0) -> list:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, cluster_key, title, problem_description, "
                "target_audience, aida_stage, intent_score, score_reasoning, "
                "confidence, evidence_count, source_urls, desired_features, "
                "price_sensitivity, common_objections, suggested_categories, "
                "latest_evidence_at, last_updated "
                "FROM buyer_needs WHERE intent_score >= :min_score "
                "ORDER BY intent_score DESC, evidence_count DESC, "
                "last_updated DESC LIMIT :limit"),
                {"min_score": min_score, "limit": limit}).mappings().all()
        return [dict(r) for r in rows]

    def get(self, need_id: str) -> dict:
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM buyer_needs WHERE id = :id"),
                {"id": need_id}).mappings().first()
        return dict(row) if row else None


class BuyerProductMatchRepository:
    def insert(self, *, need_id: str, product_url: str, product_name: str,
               merchant: str = None, verified_features: list = None,
               price_cents: int = None, commission_cents: int = None,
               commission_note: str = None, match_score: int,
               match_reasoning: str, missing_info: list = None,
               is_existing_campaign: bool = False,
               classification: str = "weak_match",
               gate_explanation: str = None,
               gate_reasons: dict = None) -> bool:
        """One candidate per (need, product_url). Returns True when NEW.
        classification + gate_reasons preserve the relevance-gate verdict so
        reports and the dashboard distinguish direct/partial/weak/unrelated
        without re-running the gate."""
        import json
        with engine.begin() as connection:
            result = connection.execute(text(
                "INSERT INTO buyer_product_matches (need_id, product_url, "
                "product_name, merchant, verified_features, price_cents, "
                "commission_cents, commission_note, match_score, "
                "match_reasoning, missing_info, is_existing_campaign, "
                "classification, gate_explanation, gate_reasons) "
                "VALUES (:n, :u, :nm, :m, :vf::jsonb, :pc, :cc, :cn, :ms, "
                ":mr, :mi::jsonb, :ex, :cls, :ge, :gr::jsonb) "
                "ON CONFLICT (need_id, product_url) DO NOTHING RETURNING id"),
                {"n": need_id, "u": product_url, "nm": product_name,
                 "m": merchant, "vf": json.dumps(verified_features or []),
                 "pc": price_cents, "cc": commission_cents,
                 "cn": commission_note, "ms": match_score, "mr": match_reasoning,
                 "mi": json.dumps(missing_info or []),
                 "ex": is_existing_campaign,
                 "cls": classification, "ge": gate_explanation,
                 "gr": json.dumps(gate_reasons or {})})
            return result.first() is not None

    def for_need(self, need_id: str) -> list:
        """Direct matches first, then partial, weak, unrelated; score breaks
        ties inside a class."""
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT * FROM buyer_product_matches WHERE need_id = :n "
                "ORDER BY CASE classification "
                "WHEN 'direct_match' THEN 0 WHEN 'partial_match' THEN 1 "
                "WHEN 'weak_match' THEN 2 ELSE 3 END, match_score DESC"),
                {"n": need_id}).mappings().all()
        return [dict(r) for r in rows]


class BuyerIntelRunRepository:
    """Daily run ledger + email idempotency sentinel."""

    def start(self, run_date: date) -> bool:
        """Returns False when this date ALREADY has a run (rerun protection)."""
        with engine.begin() as connection:
            result = connection.execute(text(
                "INSERT INTO buyer_intel_runs (run_date) VALUES (:d) "
                "ON CONFLICT (run_date) DO NOTHING RETURNING id"),
                {"d": run_date})
            return result.first() is not None

    def finish(self, run_date: date, *, sources_ok: list, sources_failed: list,
               evidence_collected: int, needs_upserted: int,
               products_matched: int, unmet_opportunities: int) -> None:
        import json
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE buyer_intel_runs SET finished_at = now(), "
                "sources_ok = :ok::jsonb, sources_failed = :bad::jsonb, "
                "evidence_collected = :ev, needs_upserted = :nn, "
                "products_matched = :pm, unmet_opportunities = :uo "
                "WHERE run_date = :d"),
                {"ok": json.dumps(sources_ok),
                 "bad": json.dumps(sources_failed), "ev": evidence_collected,
                 "nn": needs_upserted, "pm": products_matched,
                 "uo": unmet_opportunities, "d": run_date})

    def mark_email_sent(self, run_date: date) -> bool:
        """Idempotency sentinel: True ONLY for the caller that sent the
        report. A second run the same day gets False and must NOT re-send.
        A previously FAILED send leaves the column NULL and may retry."""
        with engine.begin() as connection:
            result = connection.execute(text(
                "UPDATE buyer_intel_runs SET report_email_sent_at = now() "
                "WHERE run_date = :d AND report_email_sent_at IS NULL "
                "RETURNING id"),
                {"d": run_date})
            return result.first() is not None

    def mark_email_failed(self, run_date: date, error: str) -> None:
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE buyer_intel_runs SET report_error = :e "
                "WHERE run_date = :d AND report_email_sent_at IS NULL"),
                {"e": error[:500], "d": run_date})

    def already_sent(self, run_date: date) -> bool:
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT report_email_sent_at FROM buyer_intel_runs "
                "WHERE run_date = :d"), {"d": run_date}).first()
        return bool(row and row[0])

    def get(self, run_date: date) -> dict:
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM buyer_intel_runs WHERE run_date = :d"),
                {"d": run_date}).mappings().first()
        return dict(row) if row else None
