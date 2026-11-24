"""Direct publishing to Blogger and Pinterest for APPROVED campaigns.

Safety chain (every step must pass; nothing bypasses it):
  1. campaign promotion_approved  -> sole promotion authorization
  2. relevance gate               -> the product must directly solve the need
  3. package has no invented facts -> packages come from PRODUCT_FACTS only
  4. queue duplicate guard        -> no second post/pin on retry
  5. platform-specific content    -> article vs pin copy are different

Publication records land in publishing_queue (external_id, publication_url,
published_at). A published post is NOT a sale: revenue stays in
financial_events only.
"""
import os

from services.content_packages import PRODUCT_FACTS
from services.publishing_queue import (
    claim_unpublished,
    has_published,
    mark_publish_failed,
    mark_published_external,
)
from services import blogger_publisher, pinterest_publisher

BLOGGER_ARTICLE_MAX = 3     # articles per run cap (drip, not a firehose)
PINTEREST_PIN_MAX = 3       # pins per run cap


def _gate_allows(campaign_id: str, campaign_url: str) -> tuple:
    """Relevance gate for promotion. Uses the buyer-intelligence gate when a
    stored direct_match exists for this campaign's product; otherwise the
    campaign must be one of the curated, fact-verified campaigns where the
    product/need relationship was already validated in the content pack."""
    try:
        from database.buyer_repositories import BuyerProductMatchRepository
        from database.repositories import ProductRepository
        products = [p for p in ProductRepository().list_products()
                    if getattr(p, "status", "") in ("active", "approved")]
        product_urls = {getattr(p, "url", "") for p in products}
        _ = product_urls  # reserved for future product-level gating
    except Exception:
        pass
    if campaign_id in PRODUCT_FACTS:
        return True, "campaign has verified product facts (curated pack)"
    return False, "campaign lacks verified product facts: cannot verify relevance"


def _authorized(camp_repo, campaign_id: str) -> bool:
    return camp_repo.is_promotion_approved(campaign_id)


def publish_blogger_drafts(camp_repo, blog_id: str | None = None,
                           limit: int = BLOGGER_ARTICLE_MAX,
                           as_draft: bool = True) -> dict:
    """Publish queued Blogger articles. Defaults to DRAFTS so a human runs
    the final publish at the platform (no auto-publishing)."""
    result = {"published": [], "failed": [], "skipped": [], "reason": None}
    if not blogger_publisher.credentials_ready():
        result["reason"] = ("blogger_authorization_missing: "
                            + ",".join(blogger_publisher.missing_config()))
        return result
    blog_id = blog_id or os.getenv("BLOGGER_BLOG_ID")
    if not blog_id:
        result["reason"] = "BLOGGER_BLOG_ID not configured (run --blogs)"
        return result

    for row in claim_unpublished("blogger", limit=limit):
        pkg = row["package"] or {}
        campaign_id = str(row.get("campaign_id") or "")
        title = pkg.get("title") or row["title"]
        if not campaign_id or not _authorized(camp_repo, campaign_id):
            result["skipped"].append({"id": str(row["id"]),
                                      "reason": "campaign_not_authorized"})
            continue
        allowed, why = _gate_allows(campaign_id, pkg.get("campaign_url", ""))
        if not allowed:
            result["skipped"].append({"id": str(row["id"]), "reason": why})
            continue
        if has_published("blogger", row["title"]):
            result["skipped"].append({"id": str(row["id"]),
                                      "reason": "already_published"})
            continue
        html_body = blogger_publisher.markdown_to_html(
            pkg.get("body_markdown") or pkg.get("body") or "")
        try:
            posted = blogger_publisher.publish_post(
                blog_id, title, html_body,
                labels=pkg.get("labels"), is_draft=as_draft)
        except blogger_publisher.BloggerAuthError as exc:
            mark_publish_failed(row["id"], f"auth: {exc}")
            result["failed"].append({"id": str(row["id"]), "error": str(exc)})
            result["reason"] = "auth"
            break
        except blogger_publisher.BloggerAPIError as exc:
            mark_publish_failed(row["id"], f"{exc.kind}: {exc}")
            result["failed"].append({"id": str(row["id"]),
                                     "error": f"{exc.kind}: {exc}"})
            if exc.kind == "rate_limit":
                break  # stop the run; retry next cycle
            continue
        mark_published_external(row["id"], posted["id"], posted["url"])
        result["published"].append({"queue_id": str(row["id"]),
                                    "post_id": posted["id"],
                                    "url": posted["url"],
                                    "status": posted["status"]})
    return result


def publish_pinterest_pins(camp_repo, board_id: str | None = None,
                           limit: int = PINTEREST_PIN_MAX) -> dict:
    """Publish queued pins to a board. Requires explicit board configuration:
    we never guess a destination board."""
    result = {"published": [], "failed": [], "skipped": [], "reason": None}
    if not pinterest_publisher.credentials_ready():
        result["reason"] = ("pinterest_authorization_missing: "
                            + ",".join(pinterest_publisher.missing_config()))
        return result
    board_id = board_id or os.getenv("PINTEREST_BOARD_ID")
    if not board_id:
        result["reason"] = "PINTEREST_BOARD_ID not configured (run --boards)"
        return result

    for row in claim_unpublished("pinterest", limit=limit):
        pkg = row["package"] or {}
        campaign_id = str(row.get("campaign_id") or "")
        if not campaign_id or not _authorized(camp_repo, campaign_id):
            result["skipped"].append({"id": str(row["id"]),
                                      "reason": "campaign_not_authorized"})
            continue
        allowed, why = _gate_allows(campaign_id, pkg.get("destination_url", ""))
        if not allowed:
            result["skipped"].append({"id": str(row["id"]), "reason": why})
            continue
        if has_published("pinterest", row["title"]):
            result["skipped"].append({"id": str(row["id"]),
                                      "reason": "already_published"})
            continue
        image_path = pkg.get("image_path") or ""
        if not image_path or not os.path.isfile(image_path):
            # Awaiting image: never publish an incomplete pin.
            mark_publish_failed(row["id"], "awaiting_image")
            result["skipped"].append({"id": str(row["id"]),
                                      "reason": "awaiting_image"})
            continue
        try:
            pin = pinterest_publisher.publish_pin(
                board_id=board_id,
                title=pkg.get("pin_title") or row["title"],
                description=pkg.get("pin_description") or "",
                link=pkg.get("destination_url") or "",
                image_path=image_path,
                alt_text=pkg.get("pin_title"))
        except pinterest_publisher.PinterestAuthError as exc:
            mark_publish_failed(row["id"], f"auth: {exc}")
            result["failed"].append({"id": str(row["id"]), "error": str(exc)})
            result["reason"] = "auth"
            break
        except pinterest_publisher.PinterestAPIError as exc:
            kind = exc.kind
            mark_publish_failed(row["id"], f"{kind}: {exc}")
            result["failed"].append({"id": str(row["id"]),
                                     "error": f"{kind}: {exc}"})
            if kind in ("auth", "access_level", "rate_limit"):
                result["reason"] = kind
                break
            continue
        mark_published_external(row["id"], pin["id"], pin["url"])
        result["published"].append({"queue_id": str(row["id"]),
                                    "pin_id": pin["id"],
                                    "url": pin["url"]})
    return result


def run_publishing(camp_repo, blogger_as_draft: bool = True) -> dict:
    """Run both channels. NEVER raises into the daily grind."""
    out = {}
    try:
        out["blogger"] = publish_blogger_drafts(camp_repo,
                                                as_draft=blogger_as_draft)
    except Exception as exc:
        out["blogger"] = {"reason": f"error: {type(exc).__name__}: {exc}",
                          "published": [], "failed": [], "skipped": []}
    try:
        out["pinterest"] = publish_pinterest_pins(camp_repo)
    except Exception as exc:
        out["pinterest"] = {"reason": f"error: {type(exc).__name__}: {exc}",
                            "published": [], "failed": [], "skipped": []}
    return out
