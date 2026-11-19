# Lovelyn — Your Manual Steps (updated 2026-11-19)

The code is done and passing 175 tests. Everything below is **your** side.
Each item directly gates revenue — skip them and the agent runs flawlessly for $0.

Do them in this exact order.

---

## 1. Run one SQL migration (2 min, once)

Open the **Supabase SQL editor** and run `database/migrations/add_publication_urls.sql`.
This lets the agent record *where* each article was published so attribution
(Publication → Click → Conversion) can close and the optimizer learns which
channel pays.

---

## 2. Affiliate links — THE money switch (~30 min/merchant)

Without a tracked link, every CTA on the site pays you $0.

1. If you have not yet run `database/migrations/add_monetization.sql` (the
   `affiliate_url` column), run it in the Supabase SQL editor.
2. Join affiliate programs (fastest approvals first):
   - **Payhip** — instant, built-in affiliate links
   - **ShareASale / Impact / CJ**
   - **Amazon Associates** — apply anyway; needs 3 sales in 180 days
3. Dashboard → **Products** → open each product's **"💰 Affiliate link"**
   expander → paste your tracked URL → Save.
4. Next daily run rebuilds the CTAs with your links.

---

## 3. Create ONE owned product — the only stream that pays in 30 days (~2–4 h, once)

1. Make one small digital product ($7–$15): budget-planner template,
   trading-journal checklist, or declutter guide.
2. List it on **Payhip** (free, instant) or Gumroad.
3. Put the checkout URL in `.env` AND GitHub repo Secrets:
   ```
   OWNED_PRODUCT_URL=https://payhip.com/b/YOURID
   ```
4. Every campaign page now shows a second "Buy" button.

---

## 4. Set the niche keyword (2 min, once)

In `.env` AND GitHub Secrets:
```
SITE_NICHE_KEYWORD=budget planner
```
Turns generic headlines into long-tail phrases people actually search for.
Missing keyword = generic pages = no search traffic.

---

## 5. Re-enable Dev.to distribution (5 min, once)

`DEVTO_API_KEY` is commented out in `.env`. Create a free dev.to account,
get the API key (Settings → Extensions → DEV Community API Keys), then
uncomment and set it in `.env` AND GitHub Secrets. Dev.to posts get real
search traffic; Bluesky alone does not.

---

## 6. Index the site with Google (10 min, once)

The agent now pings Bing/Yandex (IndexNow) automatically. **Google** you do once:

1. Verify `lovelyn.matchqip.com` in Google Search Console
   (the `docs/google2a56ad89c8bb6030.html` file is already there for verification).
2. Submit `https://lovelyn.matchqip.com/sitemap.xml`.
3. Request indexing for `index.html` to speed up the first crawl.

---

## 7. Daily: Reddit leads (15 min/day — the highest-intent traffic)

Dashboard → **Leads** → copy the pre-written draft reply → edit to fit the
thread → post **as yourself in your browser** → "Mark contacted".
Leads older than ~48 h are cold. Miss a day = money left on the table.

---

## 8. Weekly: post the queued content packages (20 min/week)

Dashboard → **Leads queue** holds YouTube Short scripts, Blogger drafts, and
Pinterest pins the agent already wrote. Publishing a Blogger post is the
cheapest new backlink/traffic channel — do those first. After posting, mark
the item "published" and paste the live URL so attribution records it.

---

## 9. Verify the loop end-to-end (10 min, once — your first money test)

Click your own affiliate link in an incognito window and buy your own product.
Confirm:
- the URL you land on contains your affiliate tag
- Dashboard → Finance shows the sale under the correct stream
- Dashboard → Integrations shows gumroad/payhip "connected"

---

## 30-day sequence

| Days | Do |
|------|----|
| 1    | Migration (item 1), affiliate links (item 2), niche keyword (item 4) |
| 2–5  | Build + list the owned product (item 3), Dev.to key (item 5), Search Console (item 6) |
| 3–30 | Daily: Reddit leads (item 7); weekly: queued packages (item 8) |
| 7+   | First dollars realistically arrive via owned product + Payhip affiliates |

## If you only do three things

1. **Affiliate links** (item 2) — the money switch.
2. **One owned product** (item 3) — the fastest first dollar.
3. **Daily Reddit replies** (item 7) — the only traffic that converts in week one.
