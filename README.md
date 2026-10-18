# Lovelyn — Commerce and Revenue Intelligence Platform

A cloud-based personal commerce intelligence platform that identifies,
evaluates, promotes, and monetizes legitimate product opportunities.
Two revenue streams are tracked separately: affiliate commissions and
owned-product profit. **Estimates are never reported as earned money.**

## Local setup (Windows)

1. Install Python 3.10+ and VS Code.
2. Open this folder in VS Code and open the terminal.
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in real values.
5. Run tests: `python -m pytest tests -q`
6. Run the app: `python -m streamlit run app.py`

## Environment variables

See `.env.example`. Locally they live in `.env` (never committed).
In Streamlit Community Cloud they live in app Secrets; in GitHub Actions
they live in repository Secrets (same names).

## Deployment

- Repository: public GitHub repository (required for free Streamlit Cloud and GitHub Pages).
- Dashboard: Streamlit Community Cloud (free tier), main file `app.py`, password-gated.
- Public campaign site: GitHub Pages from the `docs/` folder, rebuilt daily by the agent.
- Database: Supabase PostgreSQL (free tier); Row-Level Security enabled on all tables.
- Autonomous agent: GitHub Actions cron, daily at 08:00 UTC.

## Implementation checklist

- [x] Phase 1 — Cloud-ready foundation
- [x] Phase 2 — Persistent storage + password gate
- [x] Phase 3 — Product intelligence (safe intake, merchant ID, extraction, provenance)
- [x] Phase 4 — Explainable opportunity scoring
- [x] Phase 5 — Campaign generation and approval
- [x] Phase 6 — Authorized publishing and export
- [x] Phase 7 — Autonomous heartbeat (daily agent, GitHub Actions)
- [x] Phase 8.1 — Traffic engine (live pages, view/click tracking)
- [x] Phase 8.2 — Finance tracking (received money only) + kill/scale rules
- [ ] Phase 9 — Controlled optimization and scaling

## Financial integrity rules

- Only received money is logged, with a proof note.
- Affiliate and owned streams are never mixed.
- All money math uses integer cents.
- Targets are weekly: $50 affiliate + $50 owned = $100 combined.

## Known limitations

- Some merchants (Etsy, Payhip, etc.) refuse automated fetching; Lovelyn
  respects refusals and uses manual fallback. Official merchant APIs are
  the planned authorized route per merchant.
- Supabase pooler TLS cannot be verified from some networks; where needed,
  `LOVELYN_SSL_VERIFY=false` keeps encryption on (sslmode=require equivalent).
- Dashboard authentication is a single-owner password gate until a full
  multi-user auth phase.