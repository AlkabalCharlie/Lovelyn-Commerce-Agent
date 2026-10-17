"""Builds the public traffic site (GitHub Pages) from published campaigns."""
import html
from pathlib import Path
from urllib.parse import urlencode

from config.settings import SUPABASE_ANON_KEY, SUPABASE_USERNAME
from database.repositories import CampaignRepository

_CSS = "body{font-family:system-ui,sans-serif;margin:0;background:#f7f8fa;color:#111}" \
       ".wrap{max-width:720px;margin:0 auto;padding:32px 20px}" \
       "a.cta{display:inline-block;margin-top:24px;padding:12px 22px;background:#0f6f5c;color:#fff;border-radius:8px;text-decoration:none}" \
       "h1{line-height:1.25}"

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


def _utm(url: str, campaign_id: str) -> str:
    params = urlencode({"utm_source": "lovelyn", "utm_medium": "campaign", "utm_campaign": campaign_id[:8]})
    return f"{url}&{params}" if "?" in url else f"{url}?{params}"


def render_campaign_page(camp: dict, anon_key: str, rest_url: str) -> str:
    """Render one public campaign page. All dynamic text is HTML-escaped."""
    headline = html.escape(camp["headline"])
    body = "<br>".join(html.escape(line) for line in camp["body"].splitlines() if line.strip())
    product = html.escape(camp["product_name"])
    merchant = html.escape(camp["merchant"] or "Independent / Other")
    cta = _utm(camp["product_url"], str(camp["id"]))
    beacon = _BEACON % {"rest": rest_url, "anon": anon_key, "cid": str(camp["id"])}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{headline}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>{headline}</h1>
<p><em>{merchant} &middot; {product}</em></p>
<p>{body}</p>
<a class="cta" data-track="1" href="{html.escape(cta, quote=True)}" rel="nofollow sponsored noopener" target="_blank">View the product &rarr;</a>
</div>{beacon}</body></html>"""


def render_index(camps: list) -> str:
    items = "".join(
        f'<li><a href="campaign-{html.escape(str(c["id"]))}.html">{html.escape(c["headline"])}</a></li>'
        for c in camps
    ) or "<li>No live campaigns yet.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Lovelyn Live Campaigns</title>
<style>{_CSS}</style></head>
<body><div class="wrap"><h1>Lovelyn Live Campaigns</h1><ul>{items}</ul></div></body></html>"""


def build_site() -> int:
    """Write docs/ folder for GitHub Pages. Returns number of campaign pages."""
    if not SUPABASE_ANON_KEY:
        raise ValueError("SUPABASE_ANON_KEY missing; cannot build traffic site.")
    repo = CampaignRepository()
    camps = repo.list_published_campaigns()
    rest = _rest_url()
    out = Path("docs")
    out.mkdir(exist_ok=True)
    for camp in camps:
        (out / f"campaign-{camp['id']}.html").write_text(
            render_campaign_page(camp, SUPABASE_ANON_KEY, rest), encoding="utf-8"
        )
    (out / "index.html").write_text(render_index(camps), encoding="utf-8")
    return len(camps)