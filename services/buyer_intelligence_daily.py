"""Daily Buyer Intelligence run: research -> classify -> score -> cluster ->
match products -> persist -> email report.

Integration rules:
- Called FROM the existing autonomous agent (and standalone for backfills);
  NEVER interrupts campaign distribution or publishing: every failure mode
  returns a status string, the grind continues.
- Email is idempotent per day (buyer_intel_runs.report_email_sent_at).
- The email is a COPY: everything reported was persisted first.
"""
import json
import os
from datetime import date, datetime, timedelta, timezone

from database.buyer_repositories import (
    BuyerEvidenceRepository,
    BuyerIntelRunRepository,
    BuyerNeedsRepository,
    BuyerProductMatchRepository,
)
from database.repositories import AgentLogRepository, ProductRepository
from services.buyer_intent import (
    classify_aida,
    cluster_key_for,
    dedupe_key,
    score_band,
    score_buyer_intent,
)
from services.buyer_product_matching import recommend_for_need
from services.buyer_sources import collect_all

REPORT_RECIPIENT_DEFAULT = "chuka.cokafor@gmail.com"
MAX_NEEDS_PER_RUN = 15
MAX_PRODUCTS_PER_NEED = 8

# Distinct research term seeds - actual buyer language, not brand names.
SEARCH_TERMS = [
    "looking for a tool that", "is there an app to", "worth buying",
    "where can i buy", "recommend a", "cheaper alternative to",
    "struggling to keep track of", "how do i organize my",
    "anyone know a good", "wish there was a tool",
]


def _need_title(cluster_evidence):
    """Short need title from the cluster's most representative post title."""
    titles = [e["title"] for e in cluster_evidence if e.get("title")]
    if not titles:
        return "Unclustered buyer signal"
    # shortest informative title tends to be the crispest question
    return max(sorted(titles, key=len)[:3], key=len)[:120]


def _extract_features(text_value):
    """Crude desired-feature extraction: noun phrases after feature verbs.
    Keeps cluster cards factual (quoted fragments, never invented)."""
    import re
    fragments = re.findall(
        r"(?:something that|i need it to|must have|needs to|that can|which can)"
        r"\s+([a-z0-9 ,\-]{4,60})", (text_value or "").lower())
    return [f.strip(" ,.-") for f in fragments][:4]


def run_buyer_intelligence(run_date: date = None, session=None) -> dict:
    """One full research cycle. Returns a status dict; NEVER raises into the
    agent's daily grind."""
    run_date = run_date or date.today()
    log_repo = AgentLogRepository()
    run_repo = BuyerIntelRunRepository()

    status = {"run_date": str(run_date), "evidence": 0, "needs": 0,
              "matched": 0, "unmet": 0, "email_sent": False,
              "email_reason": None, "skipped_reason": None}

    try:
        if not run_repo.start(run_date):
            status["skipped_reason"] = "already_ran_today"
            log_repo.log_action("BUYER_INTEL",
                                f"{run_date}: already ran; skipping (duplicate guard).")
            return status
    except Exception as exc:
        status["skipped_reason"] = f"db_unavailable: {type(exc).__name__}"
        return status

    # ---- 1-2. Research + evidence collection ------------------------------
    evidence_records, sources_ok, sources_failed = [], [], []
    new_evidence = 0
    try:
        evidence_records, sources_ok, sources_failed = collect_all(
            SEARCH_TERMS, session=session)
    except Exception as exc:
        sources_failed.append(f"collect_all: {type(exc).__name__}")
        log_repo.log_action("BUYER_INTEL",
                            f"Research collection failed: {type(exc).__name__}.")

    evidence_repo = BuyerEvidenceRepository()
    staged = []          # (row, score_result)
    for rec in evidence_records:
        try:
            text_all = f"{rec.get('title', '')} {rec.get('body', '')}"
            verdict = score_buyer_intent(text_all)
            if verdict["stage"] == "none":
                continue  # not buyer-relevant: do not pollute the store
            key = dedupe_key(rec["source"], rec["source_url"],
                             rec.get("author") or "", rec.get("title") or "")
            inserted = evidence_repo.insert(
                dedupe_key=key, source=rec["source"],
                source_url=rec["source_url"], title=rec["title"],
                author=rec.get("author") or None, body=rec.get("body"),
                context=rec.get("context"), published_at=rec.get("published_at"),
                aida_stage=verdict["stage"], raw_scores=verdict["evidence"])
            if inserted:
                new_evidence += 1
            staged.append((dict(rec, dedupe_key=key), verdict))
        except Exception:
            continue  # one malformed record never aborts the run

    # ---- 3-5. Cluster into recurring needs --------------------------------
    clusters = {}
    for row, verdict in staged:
        ck = cluster_key_for(row["title"], row.get("body") or "")
        entry = clusters.setdefault(ck, {"rows": [], "verdicts": []})
        entry["rows"].append(row)
        entry["verdicts"].append(verdict)

    needs_repo = BuyerNeedsRepository()
    needs_upserted = 0
    need_ids = []
    for ck, bundle in sorted(
            clusters.items(),
            key=lambda kv: max(v["score"] for v in kv[1]["verdicts"]),
            reverse=True)[:MAX_NEEDS_PER_RUN]:
        rows = bundle["rows"]
        verdicts = bundle["verdicts"]
        distinct_authors = {r.get("author") or r["source_url"]
                            for r in rows}
        evidence_count = len(distinct_authors)  # independent discussions only
        best = max(verdicts, key=lambda v: v["score"])
        avg_score = round(sum(v["score"] for v in verdicts) / len(verdicts))
        blended = round((best["score"] + avg_score) / 2)
        stage = max(verdicts, key=lambda v: v["score"])["stage"]
        if stage == "none":
            stage = "attention"
        source_urls = [r["source_url"] for r in rows][:12]
        latest = max((r.get("published_at") or "") for r in rows) or None
        combined_text = " ".join(r["title"] + " " + (r.get("body") or "")
                                 for r in rows)
        features = _extract_features(combined_text)
        objections = [v for v in
                      ("scam", "too expensive", "is it worth", "refund")
                      if v in combined_text.lower()]
        price_note = None
        import re as _re
        m = _re.search(r"(?:under|around|budget of)\s*\$?\s*(\d+)",
                       combined_text.lower())
        if m:
            price_note = f"budget signals around ${m.group(1)}"
        try:
            nid = needs_repo.upsert(
                cluster_key=ck, title=_need_title(rows),
                problem_description=max(
                    (rows), key=lambda r: len(r.get("body") or ""))["title"],
                target_audience=(rows[0].get("context") or "") or None,
                aida_stage=stage, intent_score=blended,
                score_reasoning=" | ".join(best["reasoning"])[:2000],
                observed=sorted(set(best["observed"])),
                inferred=sorted(set(best["inferred"])),
                evidence_count=evidence_count, source_urls=source_urls,
                latest_evidence_at=latest, desired_features=features,
                price_sensitivity=price_note,
                common_objections=objections,
                unmet_aspects=[], suggested_categories=[])
            if nid:
                needs_upserted += 1
                need_ids.append(nid)
        except Exception:
            continue

    # ---- 6-7. Product discovery + matching --------------------------------
    matches_repo = BuyerProductMatchRepository()
    products_matched = 0
    unmet = []
    try:
        products = [p for p in ProductRepository().list_products()
                    if (p.status or "") in ("active", "approved")]
    except Exception:
        products = []
    for nid in need_ids:
        try:
            need = needs_repo.get(nid)
            if not need:
                continue
            verdicts = recommend_for_need(need, products[:MAX_PRODUCTS_PER_NEED])
            any_recommended = False
            for verdict in verdicts:
                if verdict["match_score"] < 40:
                    continue
                product = verdict["product"]
                matches_repo.insert(
                    need_id=nid,
                    product_url=(product.url if hasattr(product, "url")
                                 else product.get("url", "")),
                    product_name=(product.name if hasattr(product, "name")
                                  else product.get("name", "")),
                    merchant=(product.merchant if hasattr(product, "merchant")
                              else product.get("merchant")),
                    verified_features=verdict["verified_features"],
                    price_cents=(product.price if hasattr(product, "price")
                                 else product.get("price")),
                    match_score=verdict["match_score"],
                    match_reasoning=verdict["match_reasoning"],
                    missing_info=verdict["missing_info"])
                products_matched += 1
                any_recommended = True
            if not any_recommended:
                unmet.append(need)
        except Exception:
            continue

    run_repo.finish(run_date, sources_ok=sources_ok,
                    sources_failed=sources_failed,
                    evidence_collected=new_evidence,
                    needs_upserted=needs_upserted,
                    products_matched=products_matched,
                    unmet_opportunities=len(unmet))

    status.update({"evidence": new_evidence, "needs": needs_upserted,
                   "matched": products_matched, "unmet": len(unmet)})

    # ---- 8-10. Report generation + idempotent send ------------------------
    try:
        report_text = build_daily_report(run_date)
        subject = f"Lovelyn Daily Buyer Intelligence Report — {run_date}"
        from services import gmail_report
        ok, result = gmail_report.send_report(subject, report_text)
        if ok:
            if run_repo.mark_email_sent(run_date):
                status["email_sent"] = True
                log_repo.log_action("BUYER_INTEL",
                                    f"{run_date}: daily buyer intelligence report sent.")
            else:
                status["email_reason"] = "already_sent_elsewhere"
        else:
            run_repo.mark_email_failed(run_date, result)
            status["email_reason"] = result
            log_repo.log_action("BUYER_INTEL",
                                f"{run_date}: report email NOT sent ({result[:120]}).")
    except Exception as exc:
        run_repo.mark_email_failed(run_date, str(exc))
        status["email_reason"] = f"{type(exc).__name__}: {exc}"

    log_repo.log_action(
        "BUYER_INTEL",
        f"{run_date}: evidence +{new_evidence} (sources ok={len(sources_ok)}, "
        f"failed={len(sources_failed)}), needs upserted={needs_upserted}, "
        f"product matches={products_matched}, unmet={len(unmet)}, "
        f"email_sent={status['email_sent']}.")
    return status


# ---------------------------------------------------------------- report ----
def build_daily_report(run_date: date = None) -> str:
    """Human-readable consolidated report from PERSISTED data only."""
    run_date = run_date or date.today()
    run_repo = BuyerIntelRunRepository()
    needs_repo = BuyerNeedsRepository()
    matches_repo = BuyerProductMatchRepository()

    run = run_repo.get(run_date) or {}
    lines = []
    lines.append("LOVELYN DAILY BUYER INTELLIGENCE")
    lines.append("=" * 60)
    lines.append(f"Report date: {run_date}")

    needs = needs_repo.top_needs(limit=20)
    bands = {"high_intent": 0, "strong_opportunity": 0,
             "developing_demand": 0, "early_awareness": 0}
    total_evidence = sum(n.get("evidence_count") or 0 for n in needs)
    for n in needs:
        bands[score_band(n["intent_score"])] += 1

    # ---- Executive summary ----
    lines.append("")
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 60)
    lines.append(f"Buyer needs tracked:            {len(needs)}")
    lines.append(f"High purchase intent (80-100):  {bands['high_intent']}")
    lines.append(f"Strong opportunities (60-79):   {bands['strong_opportunity']}")
    lines.append(f"Developing demand (40-59):      {bands['developing_demand']}")
    lines.append(f"Independent discussions:        {total_evidence}")
    lines.append(f"Sources investigated OK:        {len(run.get('sources_ok') or [])}"
                 f" {json.dumps(run.get('sources_ok') or [])}")
    lines.append(f"Sources failed/unavailable:     {len(run.get('sources_failed') or [])}"
                 f" {json.dumps(run.get('sources_failed') or [])}")
    lines.append(f"Evidence collected today:       {run.get('evidence_collected', 0)}")

    # ---- Top buyer opportunities ----
    lines.append("")
    lines.append("TOP BUYER OPPORTUNITIES")
    lines.append("-" * 60)
    if not needs:
        lines.append("(no buyer needs recorded yet)")
    for i, n in enumerate(needs[:5], 1):
        lines.append(f"\n{i}. {n['title']}")
        lines.append(f"   Problem      : {n['problem_description'][:150]}")
        lines.append(f"   Audience     : {n.get('target_audience') or 'n/a'}")
        lines.append(f"   AIDA stage   : {n['aida_stage']}")
        lines.append(f"   Intent score : {n['intent_score']}/100 "
                     f"({score_band(n['intent_score'])})")
        lines.append(f"   Confidence   : {n['confidence']} "
                     f"({n['evidence_count']} independent discussion(s))")
        urls = json.loads(n.get("source_urls") or "[]")
        for u in urls[:3]:
            lines.append(f"   Evidence     : {u}")
        feats = json.loads(n.get("desired_features") or "[]")
        lines.append(f"   Wanted       : {'; '.join(feats[:3]) or 'not stated'}")
        lines.append(f"   Price        : {n.get('price_sensitivity') or 'not stated'}")
        objs = json.loads(n.get("common_objections") or "[]")
        lines.append(f"   Objections   : {'; '.join(objs[:3]) or 'none recorded'}")

    # ---- Product discovery findings ----
    lines.append("")
    lines.append("PRODUCT DISCOVERY FINDINGS")
    lines.append("-" * 60)
    found_any = False
    for n in needs[:5]:
        matches = matches_repo.for_need(n["id"])
        for m in matches[:2]:
            found_any = True
            price = (f"${m['price_cents']/100:.2f}"
                     if m.get("price_cents") is not None else "UNVERIFIED")
            lines.append(f"\n- {m['product_name']} -> need: {n['title'][:60]}")
            lines.append(f"  URL: {m['product_url']}")
            lines.append(f"  Match score: {m['match_score']}/100")
            lines.append(f"  Price: {price} | Merchant: "
                         f"{m.get('merchant') or 'unverified'}")
            if m.get('commission_cents') is not None:
                commission = f"${m['commission_cents'] / 100:.2f}"
            else:
                commission = 'unverified'
            lines.append(f"  Commission: {commission} "
                         f"{m.get('commission_note') or ''}")
            lines.append(f"  Why: {m['match_reasoning'][:200]}")
            missing = json.loads(m.get("missing_info") or "[]")
            if missing:
                lines.append(f"  Missing info: {'; '.join(missing)}")
            lines.append(f"  Already authorized campaign: "
                         f"{bool(m.get('is_existing_campaign'))}")
    if not found_any:
        lines.append("(no product matches yet)")

    # ---- Unmet market opportunities ----
    lines.append("")
    lines.append("UNMET MARKET OPPORTUNITIES")
    lines.append("-" * 60)
    unmet = [n for n in needs if not matches_repo.for_need(n["id"])]
    if not unmet:
        lines.append("(none today)")
    for n in unmet:
        lines.append(f"- [{n['intent_score']}/100] {n['title']} "
                     f"({n['aida_stage']}, {n['confidence']} confidence)")
    lines.append("(these feed tomorrow's product discovery)")

    # ---- Tomorrow's research priorities ----
    lines.append("")
    lines.append("TOMORROW'S RESEARCH PRIORITIES")
    lines.append("-" * 60)
    for n in needs[:3]:
        lines.append(f"- '{n['title']}' (score {n['intent_score']}, "
                     f"{n['evidence_count']} discussion(s)): growing cluster "
                     f"with {'high' if n['intent_score'] >= 80 else 'real'} "
                     f"purchase signals; verify product availability.")

    # ---- Commercial learning (verified money ONLY) ----
    lines.append("")
    lines.append("COMMERCIAL LEARNING (verified money only)")
    lines.append("-" * 60)
    try:
        from database.repositories import CampaignRepository, FinanceRepository
        from models.finance import format_cents
        week_ago = run_date - timedelta(days=7)
        totals = FinanceRepository().sum_by_stream_since(week_ago)
        lines.append(f"Verified affiliate received (7d): "
                     f"{format_cents(totals.get('affiliate', 0))}")
        lines.append(f"Verified owned received (7d):     "
                     f"{format_cents(totals.get('owned', 0))}")
        stats = CampaignRepository().get_traffic_stats()
        visits = sum(r.get("views") or 0 for r in stats)
        clicks = sum(r.get("clicks") or 0 for r in stats)
        lines.append(f"Campaign visits (lifetime):       {visits}")
        lines.append(f"Checkout clicks (lifetime):       {clicks}")
        lines.append("(test events, estimates and unverified purchases are "
                     "never reported as revenue)")
    except Exception as exc:
        lines.append(f"(commercial section unavailable: {type(exc).__name__})")

    lines.append("")
    lines.append("Research is observation, not validation; validation is not "
                 "revenue. Only verified financial_events count as money.")
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_buyer_intelligence()
    print(json.dumps(result, indent=2, default=str))
