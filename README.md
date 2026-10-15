# Lovelyn — Commerce and Revenue Intelligence Platform

A cloud-based personal commerce intelligence platform that identifies,
evaluates, promotes, and monetizes legitimate product opportunities.
Two revenue streams are tracked separately: affiliate commissions and
owned-product profit. Estimates are never reported as earned money.

## Local setup (Windows)

1. Install Python 3.10+ and VS Code.
2. Open this folder in VS Code and open the terminal.
3. Create and activate a virtual environment (optional but recommended):
   - `python -m venv venv`
   - `.\venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in real values.
6. Run tests: `python -m pytest tests -q`
7. Run the app: `python -m streamlit run app.py`

## Environment variables

See `.env.example`. Locally they live in `.env` (never committed).
In Streamlit Community Cloud they live in app Secrets (same names).

## Deployment

- Repository: private GitHub repository.
- Dashboard: Streamlit Community Cloud (free tier), main file `app.py`.
- Database: Supabase PostgreSQL (free tier), schema managed via SQL migrations.

## Implementation checklist

- [x] Phase 1 — Cloud-ready foundation (dashboard live on Streamlit Cloud)
- [x] Phase 2 — Persistent storage (Supabase, products CRUD, search/filter/status)
- [x] Phase 2 close-out — password gate, error hardening, tests, README
- [ ] Phase 3 — Product intelligence (safe URL intake, merchant ID, extraction)
- [ ] Phase 4 — Opportunity research and scoring
- [ ] Phase 5 — Campaign generation and approval
- [ ] Phase 6 — Authorized publishing
- [ ] Phase 7 — Scheduling and autonomous research
- [ ] Phase 8 — Analytics and financial reconciliation
- [ ] Phase 9 — Controlled optimization

## Known limitations

- Supabase pooler endpoint does not pass strict TLS certificate verification
  from some networks (including Streamlit Cloud). Where required,
  `LOVELYN_SSL_VERIFY=false` keeps the connection encrypted
  (sslmode=require equivalent) without chain verification. Revisit during
  security hardening (direct endpoint or Supabase HTTPS API).
- The dashboard password gate is a single-owner interim measure until a
  full authentication phase is implemented.
- Streamlit Community Cloud apps sleep when idle; background work will use
  scheduled jobs (Phase 7), not an always-on worker.