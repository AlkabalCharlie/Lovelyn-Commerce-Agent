# Lovelyn — Your Manual Steps (the human part of the machine)

The agent automates enrichment, generation, distribution, and optimization.
These are the steps **only you** can do. Each one directly gates revenue —
skip them and the agent runs flawlessly for $0.

---

## 1. Affiliate links — THE money switch (do this first, ~30 min/merchant)

Without a tracked link, every campaign CTA pays you nothing.

1. Create an `affiliate_url` column: open the **Supabase SQL editor** and run
   `database/migrations/add_monetization.sql`.
2. Join 2–3 affiliate programs that accept new affiliates quickly:
   - **Payhip** — instant, built-in affiliate links (good first win)
   - **ShareASale / Impact / CJ** — faster approval than Amazon
   - **Amazon Associates** — slow to approve; apply anyway, needs 3 sales in 180 days
3. In the dashboard → **Products** page, open each product's
   **"💰 Affiliate link"** expander and paste your tracked URL. Save.
4. Next daily run, the rebuilt site CTAs use your link instead of the raw URL.
   *Until you do this, the CTA honestly links straight to the merchant — and earns $0.*

## 2. Owned product — the only stream that pays in 30 days (~2–4 h, once)

1. Make one small digital product ($7–$15): a budget-planner template,
   trading-journal checklist, or declutter guide — built from the product
   research the agent already collects.
2. List it on **Payhip** (free, instant) or Gumroad.
3. Copy the checkout URL into `.env` (and GitHub repo Secrets → and Streamlit
   secrets) as:
   ```
   OWNED_PRODUCT_URL=https://payhip.com/b/YOURID
   ```
   Every campaign page now shows a second "Buy" button above the disclosure.

## 3. Niche keyword — makes headlines searchable (~2 min, once)

Set in `.env` / Secrets:
```
SITE_NICHE_KEYWORD=budget planner        (or day trading journal, debt tracker...)
```
Headlines change from `Product Review (Etsy)` to long-tail buyer-intent
phrases people actually type. Unset = generic phrases.

## 4. Reddit leads — highest-intent traffic, answers expire (~15 min/day)

Dashboard → **Leads**: each lead now has a **draft reply** pre-written with an
affiliate disclosure. Copy → edit to fit the thread → post **as yourself in
your browser** → "Mark contacted". Posts older than ~48 h are cold; do them
daily. The bot never posts.

## 5. Rewrite backlog — skim weekly (~5 min/week)

Dashboard → **Agent Logs**, look for `REWRITE`: pages with zero traffic after
5 days got a keyword-angled replacement. Give the fresh headline a sanity
read once a week.

## 6. Verify the loop (first money test)

After doing #1 and #2: click your own affiliate link once (in an incognito
window) and buy the owned product. Confirm:
- the click lands on a URL containing your affiliate tag
- the Payhip/Gumroad webhook (already wired) logs a row in `financial_events`
- Dashboard → Finance shows it under the correct stream

---

## Suggested 30-day sequence

| Days | Do |
|------|----|
| 1–2  | Run migration, join Payhip affiliates, paste links (item 1), set niche keyword (item 3) |
| 2–5  | Build + list the owned product (item 2) |
| 3–30 | Daily: Reddit leads (item 4); weekly: rewrite backlog (item 5) |
| 7+   | First dollars realistically arrive via owned product + Payhip affiliates |
