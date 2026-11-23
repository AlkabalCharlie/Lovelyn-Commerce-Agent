"""Dashboard tab: Buyer Intelligence (AIDA engine results).

Read-only view over buyer_needs / buyer_product_matches /
buyer_intel_runs. No separate dashboard: rendered through the existing
Streamlit navigation in app.py.
"""
import json
from datetime import date

import streamlit as st

from database.buyer_repositories import (
    BuyerIntelRunRepository,
    BuyerNeedsRepository,
    BuyerProductMatchRepository,
)
from services.buyer_intent import score_band

st.title("Buyer Intelligence")
st.caption("AIDA buyer-need research, intent scoring and product matching. "
           "Research ≠ demand validation ≠ revenue.")

needs_repo = BuyerNeedsRepository()
matches_repo = BuyerProductMatchRepository()
runs_repo = BuyerIntelRunRepository()

needs = needs_repo.top_needs(limit=30)
if not needs:
    st.info("No buyer needs recorded yet. The daily grind populates this "
            "from public research sources.")
    st.stop()

bands = {"high_intent": [], "strong_opportunity": [], "developing_demand": [],
         "early_awareness": []}
for n in needs:
    bands[score_band(n["intent_score"])].append(n)

col1, col2, col3, col4 = st.columns(4)
col1.metric("High intent (80-100)", len(bands["high_intent"]))
col2.metric("Strong opportunity (60-79)", len(bands["strong_opportunity"]))
col3.metric("Developing (40-59)", len(bands["developing_demand"]))
col4.metric("Independent discussions",
            sum(n.get("evidence_count") or 0 for n in needs))

st.divider()

tab_needs, tab_unmet, tab_runs = st.tabs(
    ["Top buyer needs", "Unmet opportunities", "Research history"])

with tab_needs:
    for n in needs[:15]:
        with st.expander(
                f"[{n['intent_score']}/100 · {n['aida_stage']} · "
                f"{n['confidence']}] {n['title']}"):
            st.markdown(f"**Problem:** {n['problem_description']}")
            st.markdown(f"**Audience:** {n.get('target_audience') or 'n/a'}")
            st.markdown(f"**Why this score:** {n['score_reasoning']}")
            urls = json.loads(n.get("source_urls") or "[]")
            if urls:
                st.markdown("**Evidence:**")
                for u in urls[:6]:
                    st.markdown(f"- {u}")
            feats = json.loads(n.get("desired_features") or "[]")
            if feats:
                st.markdown(f"**Desired features:** {', '.join(feats)}")
            if n.get("price_sensitivity"):
                st.markdown(f"**Price sensitivity:** {n['price_sensitivity']}")
            objs = json.loads(n.get("common_objections") or "[]")
            if objs:
                st.markdown(f"**Common objections:** {', '.join(objs)}")
            matches = matches_repo.for_need(n["id"])
            if matches:
                st.markdown("**Product matches:**")
                for m in matches:
                    price = (f"${m['price_cents']/100:.2f}"
                             if m.get("price_cents") is not None
                             else "price unverified")
                    cls = m.get("classification") or "unclassified"
                    badge = {"direct_match": "🟢 DIRECT (promotable)",
                             "partial_match": "🟡 PARTIAL (research only)",
                             "weak_match": "🟠 WEAK (rejected)",
                             "unrelated": "🔴 UNRELATED (rejected)"}.get(
                        cls, cls)
                    st.markdown(
                        f"- **{badge}** [{m['match_score']}/100] "
                        f"[{m['product_name']}]({m['product_url']}) — {price} "
                        f"({'authorized campaign' if m['is_existing_campaign'] else 'no authorized campaign (separate owner decision)'})")
                    if m.get("gate_explanation"):
                        st.caption(f"Gate: {m['gate_explanation']}")
                    st.caption(m["match_reasoning"])
                    missing = json.loads(m.get("missing_info") or "[]")
                    if missing:
                        st.caption("Missing: " + "; ".join(missing))
            else:
                st.warning("No suitable product identified yet — unmet "
                           "market opportunity (feeds next product discovery).")

with tab_unmet:
    unmet = [n for n in needs
             if not matches_repo.for_need(n["id"])]
    if unmet:
        for n in unmet:
            st.markdown(
                f"- **[{n['intent_score']}/100]** {n['title']} "
                f"({n['aida_stage']}, {n['confidence']} confidence, "
                f"{n['evidence_count']} discussion(s))")
    else:
        st.success("Every tracked buyer need has at least one evaluated "
                   "product candidate.")

with tab_runs:
    st.subheader("Daily research history")
    today = date.today()
    row = runs_repo.get(today)
    if row:
        st.markdown(f"**Today ({today}):** evidence "
                    f"{row.get('evidence_collected', 0)}, needs "
                    f"{row.get('needs_upserted', 0)}, matches "
                    f"{row.get('products_matched', 0)}, unmet "
                    f"{row.get('unmet_opportunities', 0)}")
        st.markdown(f"- Sources OK: {json.dumps(row.get('sources_ok') or [])}")
        st.markdown(f"- Sources failed: "
                    f"{json.dumps(row.get('sources_failed') or [])}")
        sent = row.get("report_email_sent_at")
        if sent:
            st.success(f"Report email sent: {sent}")
        elif row.get("report_error"):
            st.error(f"Report email failed: {row['report_error']}")
        else:
            st.warning("Report email not yet sent today.")
    else:
        st.info("No research run recorded today yet.")
