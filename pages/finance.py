"""Finance page: received money, net profit, attribution, integration health."""
from datetime import date, timedelta

import streamlit as st

from database.repositories import FinanceRepository
from models.finance import (
    VALID_STREAMS,
    FinanceValidationError,
    FinancialEvent,
    format_cents,
    parse_amount_to_cents,
)

st.title("Finance")
st.caption("Received money only. Estimates and pending commissions are never "
           "counted as revenue.")

repo = FinanceRepository()

with st.form("finance_form", clear_on_submit=True):
    stream = st.selectbox("Revenue stream", VALID_STREAMS)
    amount = st.text_input("Amount received (USD) *", placeholder="12.34")
    source = st.text_input("Source (merchant / program)", placeholder="Etsy / Amazon Associates")
    note = st.text_input("Proof note (order id, payout reference)", placeholder="payout #A123")
    fees = st.text_input("Fees (optional)", placeholder="0.35")
    costs = st.text_input("Product costs / COGS (optional)", placeholder="0.00")
    received = st.date_input("Date received", value=date.today())
    submitted = st.form_submit_button("Log received money")

if submitted:
    try:
        event = FinancialEvent(
            stream=stream,
            amount_cents=parse_amount_to_cents(amount),
            source=source.strip(),
            note=note.strip(),
            received_at=received,
        )
        repo.add_event(event)
        st.success(f"Logged {format_cents(event.amount_cents)} ({stream}).")
    except FinanceValidationError as exc:
        st.error(f"Please fix the entry: {exc}")
    except Exception as exc:
        st.error("Could not save the entry. Technical details are in the server log.")
        print(f"Finance save failed: {exc}")

st.divider()
since = date.today() - timedelta(days=7)
totals = repo.sum_by_stream_since(since)
c1, c2, c3 = st.columns(3)
c1.metric("Affiliate received (7 days)", format_cents(totals.get("affiliate", 0)))
c2.metric("Owned received (7 days)", format_cents(totals.get("owned", 0)))
c3.metric("Combined (7 days)", format_cents(totals.get("affiliate", 0) + totals.get("owned", 0)))

st.divider()
st.subheader("Net profit (verified only)")
st.caption("net = verified sales − refunds − platform fees − product costs. "
           "Pending commissions are never counted; refunds subtract fully.")
try:
    net = repo.net_profit_summary()
    if net:
        nc1, nc2, nc3, nc4 = st.columns(4)
        aff = net.get("affiliate", {"gross_cents": 0, "refunds_cents": 0, "costs_cents": 0, "net_cents": 0})
        own = net.get("owned", {"gross_cents": 0, "refunds_cents": 0, "costs_cents": 0, "net_cents": 0})
        nc1.metric("Affiliate net", format_cents(aff["net_cents"]),
                   f"gross {format_cents(aff['gross_cents'])}")
        nc2.metric("Owned net", format_cents(own["net_cents"]),
                   f"gross {format_cents(own['gross_cents'])}")
        nc3.metric("Refunds total",
                   format_cents(aff["refunds_cents"] + own["refunds_cents"]))
        nc4.metric("Combined net",
                   format_cents(aff["net_cents"] + own["net_cents"]))
    else:
        st.info("No financial events yet - net profit appears after the first verified transaction.")
except Exception as exc:
    st.warning("Net-profit view needs the Phase 2 migration "
               "(database/migrations/phase2_attribution.sql) - run it in the Supabase SQL editor.")
    print(f"Net profit load failed: {exc}")

st.divider()
st.subheader("Net profit breakdown")
if "net" in dir() and net:
    dim = st.selectbox("Group by", ["product", "campaign", "channel"])
    try:
        rows = repo.breakdown(dim)
        if rows:
            for row in rows:
                st.markdown(f"**{row['label']}** — net {format_cents(row['net_cents'])} "
                            f"from {row['verified_count']} verified transaction(s)")
        else:
            st.caption("No attributed transactions yet.")
    except Exception as exc:
        st.warning("Breakdown needs the Phase 2 migration (campaign_id/product_id columns).")
        print(f"Breakdown failed: {exc}")

st.divider()
st.subheader("Recent entries")
recent = repo.list_recent()
if not recent:
    st.info("No money logged yet. The first real commission or sale goes here.")
else:
    for row in recent:
        st.markdown(
            f"**{format_cents(row['amount_cents'])}** — {row['stream']} | "
            f"{row['source'] or 'no source'} | {row['received_at']} | proof: {row['note'] or 'none'}"
        )

st.divider()
st.subheader("Integration health")
st.caption("Live status of every external integration. A silent failure here "
           "means money silently stops arriving - check this weekly.")
_STATUS_ICON = {"connected": "🟢", "awaiting_verification": "🟡",
                "authorization_expired": "🟠", "configuration_missing": "⚪",
                "quota_exceeded": "🟣", "failed": "🔴"}
try:
    health = repo.health_status()
    if not health:
        st.caption("No integrations reporting yet. The agent and webhooks update this.")
    for row in health:
        icon = _STATUS_ICON.get(row["status"], "❔")
        ok = row["last_ok_at"].strftime("%Y-%m-%d %H:%M") if row.get("last_ok_at") else "never"
        st.markdown(f"{icon} **{row['integration']}** — {row['status']} | last OK: {ok}"
                    + (f" | {row['detail']}" if row.get("detail") else ""))
except Exception as exc:
    st.caption("Health panel needs the Phase 2 migration (integration_health table).")
    print(f"Health load failed: {exc}")