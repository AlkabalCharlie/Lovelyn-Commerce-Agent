"""Finance page: log received money only."""
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
st.caption("Received money only. Estimates are never logged here.")

repo = FinanceRepository()

with st.form("finance_form", clear_on_submit=True):
    stream = st.selectbox("Revenue stream", VALID_STREAMS)
    amount = st.text_input("Amount received (USD) *", placeholder="12.34")
    source = st.text_input("Source (merchant / program)", placeholder="Etsy / Amazon Associates")
    note = st.text_input("Proof note (order id, payout reference)", placeholder="payout #A123")
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