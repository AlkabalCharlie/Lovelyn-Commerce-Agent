"""Builds the public traffic site (GitHub Pages) from published campaigns.

Search-intent ready: meta description, robots, canonical, sitemap, robots.txt.
Compliance: FTC affiliate disclosure on every monetized page.
"""
import html
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from config.settings import (
    INITIAL_LAUNCH_CAMPAIGN_IDS,
    OWNED_PRODUCT_URL,
    SITE_BASE_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_USERNAME,
)
from database.repositories import CampaignRepository

import os as _os

_CSS = "body{font-family:system-ui,sans-serif;margin:0;background:#f7f8fa;color:#111}" \
       ".wrap{max-width:720px;margin:0 auto;padding:32px 20px}" \
       "a.cta{display:inline-block;margin-top:24px;padding:12px 22px;background:#0f6f5c;color:#fff;border-radius:8px;text-decoration:none}" \
       ".disclosure{margin-top:32px;font-size:12px;color:#666}" \
       "h1{line-height:1.25}" \
       ".hero{width:100%;max-width:720px;height:auto;border-radius:10px;display:block;margin:0 0 24px}" \
       "@media (max-width:480px){.hero{margin:0 -20px 20px;border-radius:0}}"

_DISCLOSURE = (
    '<p class="disclosure">Disclosure: if you buy through links on this page, '
    "we may earn a commission at no extra cost to you. Opinions are our own.</p>"
)

_BEACON = """
<script>
(function(){
  var rest = "%(rest)s";
  var key = "%(anon)s";
  var cid = "%(cid)s";
  function send(type){
    try{
      fetch(rest + "/rest/v1/page_events", {
        method: "POST",
        keepalive: true,
        headers: {"apikey": key, "Authorization": "Bearer " + key,
                  "Content-Type": "application/json", "Prefer": "return=minimal"},
        body: JSON.stringify({campaign_id: cid, event_type: type, page_url: location.href})
      }).then(function(r){ console.log("[lovelyn-beacon]", type, r.status); },
              function(e){ console.log("[lovelyn-beacon]", type, "network-error", e); });
    }catch(e){ console.log("[lovelyn-beacon]", type, "threw", e); }
  }
  send("view");
  document.addEventListener("click", function(ev){
    var t = ev.target;
    var a = (t && t.closest) ? t.closest("a[data-track]") : null;
    if (a) { send("click"); }
  }, true);
})();
</script>
"""


def _rest_url() -> str:
    ref = SUPABASE_USERNAME.split(".", 1)[1] if "." in SUPABASE_USERNAME else SUPABASE_USERNAME
    return f"https://{ref}.supabase.co"

# Optional homepage hero visual. Rendered as a REAL <img> (not a link, not a
# banner overlay): campaign titles/descriptions/buttons stay plain HTML.
HERO_IMAGE = "assets/lovelyn-hero.png"


def _md_to_html(text: str) -> str:
    """Minimal markdown -> HTML. Input MUST already be HTML-escaped.

    Supports exactly: '## ' headings, '### ' headings, '- ' bullet lists
    (consecutive lines), and blank-line-separated paragraphs. Anything else
    stays as plain text in a paragraph - nothing is invented.
    """
    lines = text.splitlines()
    blocks = []          # finished html chunks
    para = []            # pending plain-text lines
    bullets = []         # pending list items

    def flush_para():
        if para:
            blocks.append("<p>" + " ".join(para) + "</p>")
            para.clear()

    def flush_bullets():
        if bullets:
            blocks.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_para()
            flush_bullets()
        elif stripped.startswith("### "):
            flush_para()
            flush_bullets()
            blocks.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            flush_para()
            flush_bullets()
            blocks.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("- "):
            flush_para()
            bullets.append(stripped[2:])
        else:
            flush_bullets()
            para.append(stripped)
    flush_para()
    flush_bullets()
    return "".join(blocks)


_BUY_BUTTON = (
    '<a class="cta" data-track="owned" href="{url}" rel="noopener" '
    'target="_blank">Get the {name} toolkit &rarr;</a>'
)


def _utm(url: str, campaign_id: str) -> str:
    params = urlencode({"utm_source": "lovelyn", "utm_medium": "campaign", "utm_campaign": campaign_id[:8]})
    return f"{url}&{params}" if "?" in url else f"{url}?{params}"


def render_campaign_page(camp: dict, anon_key: str, rest_url: str, base_url: str) -> str:
    """Render one public campaign page. All dynamic text is HTML-escaped."""
    headline = html.escape(camp["headline"])
    body_lines = [line for line in camp["body"].splitlines() if line.strip()]
    # Security unchanged: escape FIRST, convert minimal markdown SECOND.
    body = _md_to_html(html.escape(camp["body"]))
    description = html.escape(body_lines[0][:150]) if body_lines else headline
    product = html.escape(camp["product_name"])
    merchant = html.escape(camp["merchant"] or "Independent / Other")
    # Monetized link first: the tracked affiliate URL if the owner set one,
    # otherwise fall back to the raw merchant URL (still disclosed honestly).
    affiliate = (camp.get("affiliate_url") or "").strip()
    # Owned products are OUR products: the honest disclosure differs.
    dest = affiliate or camp["product_url"]
    is_owned = "gumroad.com" in dest or "payhip.com" in dest
    disclosure = (
        '<p class="disclosure">Disclosure: this is our own product. If you buy '
        "through this page we receive the proceeds at no extra cost to you. "
        "Opinions are our own.</p>"
        if is_owned else _DISCLOSURE
    )
    cta = _utm(affiliate or camp["product_url"], str(camp["id"]))
    cta_label = "View the product &rarr;"
    buy_html = ""
    if OWNED_PRODUCT_URL:
        buy_html = _BUY_BUTTON.format(url=html.escape(OWNED_PRODUCT_URL, quote=True),
                                      name=html.escape(camp["product_name"]))
    canonical = f"{base_url}campaign-{camp['id']}.html"
    beacon = _BEACON % {"rest": rest_url, "anon": anon_key, "cid": str(camp["id"])}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<title>{headline}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>{headline}</h1>
<p><em>{merchant} &middot; {product}</em></p>
<p>{body}</p>
<a class="cta" data-track="1" href="{html.escape(cta, quote=True)}" rel="nofollow sponsored noopener" target="_blank">{cta_label}</a>
{buy_html}
{disclosure}
</div>{beacon}</body></html>"""


def render_index(camps: list) -> str:
    items = "".join(
        f'<li><a href="campaign-{html.escape(str(c["id"]))}.html">{html.escape(c["headline"])}</a></li>'
        for c in camps
    ) or "<li>No live campaigns yet.</li>"
    hero = ""
    if HERO_IMAGE:
        hero = (f'<img class="hero" src="{HERO_IMAGE}" width="720" height="360" '
                f'alt="Lovelyn - curated product reviews and guides" loading="eager" decoding="async">')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<title>Lovelyn Live Campaigns</title>
<style>{_CSS}</style></head>
<body><div class="wrap"><h1>Lovelyn Live Campaigns</h1>{hero}<ul>{items}</ul></div></body></html>"""


def render_sitemap(camps: list, base_url: str) -> str:
    today = date.today().isoformat()
    urls = [f"<url><loc>{base_url}index.html</loc><lastmod>{today}</lastmod></url>"]
    for c in camps:
        urls.append(f"<url><loc>{base_url}campaign-{c['id']}.html</loc><lastmod>{today}</lastmod></url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>"


def build_site(output_dir: str | None = None) -> int:
    """Write the GitHub Pages folder (default docs/). Returns # campaign pages.

    output_dir lets tests/dry-runs target a scratch folder without touching
    the real docs/ tree."""
    if not SUPABASE_ANON_KEY:
        raise ValueError("SUPABASE_ANON_KEY missing; cannot build traffic site.")
    repo = CampaignRepository()
    camps = [
        camp for camp in repo.list_published_campaigns()
        if str(camp["id"]) in INITIAL_LAUNCH_CAMPAIGN_IDS
    ]
    rest = _rest_url()
    out = Path(output_dir or "docs")
    out.mkdir(exist_ok=True)
    live_ids = {str(c["id"]) for c in camps}
    removed = 0
    for old in out.glob("campaign-*.html"):
        if old.stem.removeprefix("campaign-") not in live_ids:
            old.unlink()
            removed += 1
    if removed:
        print(f"site_builder: pruned {removed} stale campaign page(s) from {out}/")
    for camp in camps:
        (out / f"campaign-{camp['id']}.html").write_text(
            render_campaign_page(camp, SUPABASE_ANON_KEY, rest, SITE_BASE_URL), encoding="utf-8"
        )
    (out / "index.html").write_text(render_index(camps), encoding="utf-8")
    (out / "sitemap.xml").write_text(render_sitemap(camps, SITE_BASE_URL), encoding="utf-8")
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE_URL}sitemap.xml\n", encoding="utf-8"
    )
    return len(camps)