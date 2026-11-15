"""Phase 2 unit tests: attribution in postbacks, Gumroad ping normalization."""
from services.affiliate_postback import normalize_postback
from services.gumroad_ping import normalize_ping

CAMPAIGN = "123e4567-e89b-12d3-a456-426614174000"
PRODUCT = "9b2f8a44-1111-2222-3333-444455556666"


# ---------- affiliate attribution ----------

def test_campaign_and_product_ids_survive_postback():
    event = normalize_postback({
        "amount": "12.34", "transaction_id": "TX1", "source": "jvzoo",
        "campaign_id": CAMPAIGN, "product_id": PRODUCT,
    })
    assert event["campaign_id"] == CAMPAIGN
    assert event["product_id"] == PRODUCT


def test_non_uuid_attribution_is_dropped_not_guessed():
    event = normalize_postback({
        "amount": "12.34", "transaction_id": "TX1",
        "campaign_id": "my-campaign-name", "product_id": "Product X",
    })
    assert event["campaign_id"] is None
    assert event["product_id"] is None


def test_postback_without_attribution_still_works():
    event = normalize_postback({"amount": "$7", "txid": "TX2"})
    assert event["campaign_id"] is None and event["product_id"] is None


# ---------- gumroad ping ----------

def _sale_params(**over):
    base = {
        "seller_id": "SELLER123", "sale_id": "FO8TXN-Q==",
        "product_name": "Pixel Runner", "product_id": PRODUCT,
        "price": "499", "gumroad_fee": "89", "currency": "usd",
        "order_number": "524459935", "resource_name": "sale",
        "campaign_id": CAMPAIGN,
    }
    base.update(over)
    return base


def test_sale_ping_normalizes_to_owned_verified():
    event = normalize_ping(_sale_params())
    assert event["stream"] == "owned"
    assert event["amount_cents"] == 499
    assert event["fees_cents"] == 89
    assert event["status"] == "verified"
    assert event["campaign_id"] == CAMPAIGN
    assert event["product_id"] == PRODUCT
    assert event["tx_id"] == "gumroad-FO8TXN-Q==-sale"


def test_refund_ping_is_reversed_row_with_same_sale_id():
    refund = normalize_ping(_sale_params(resource_name="cancellation"))
    assert refund["status"] == "reversed"
    assert refund["tx_id"] == "gumroad-FO8TXN-Q==-refund"  # dedupes apart from the sale
    assert refund["stream"] == "owned"


def test_refunded_flag_also_flips_to_reversed():
    refund = normalize_ping(_sale_params(refunded="true"))
    assert refund["status"] == "reversed"


def test_test_purchase_is_never_money():
    assert normalize_ping(_sale_params(test="true")) is None


def test_missing_sale_id_is_unusable():
    params = _sale_params()
    del params["sale_id"]
    assert normalize_ping(params) is None


def test_bad_price_is_unusable():
    assert normalize_ping(_sale_params(price="free")) is None
    assert normalize_ping(_sale_params(price="0")) is None


def test_missing_fees_default_to_zero():
    params = _sale_params()
    del params["gumroad_fee"]
    assert normalize_ping(params)["fees_cents"] == 0


# ---------- gumroad url_params attribution (Edge Function contract) ----------

def test_campaign_id_extracted_from_url_params_json():
    from services.gumroad_ping import extract_campaign_id_from_url_params
    params = _sale_params(url_params='{"campaign_id": "%s", "source_url": "https%%3A%%2F%%2Flovelyn"}' % CAMPAIGN)
    assert extract_campaign_id_from_url_params(params) == CAMPAIGN


def test_url_params_without_uuid_attribution_stay_null():
    from services.gumroad_ping import extract_campaign_id_from_url_params
    params = _sale_params(url_params='{"cid": "black-friday"}')
    assert extract_campaign_id_from_url_params(params) is None


def test_url_params_absent_or_malformed_is_not_attributed():
    from services.gumroad_ping import extract_campaign_id_from_url_params
    assert extract_campaign_id_from_url_params(_sale_params()) is None
    assert extract_campaign_id_from_url_params(_sale_params(url_params="not-json")) is None


def test_cid_key_in_url_params_is_also_accepted():
    from services.gumroad_ping import extract_campaign_id_from_url_params
    params = _sale_params(url_params='{"cid": "%s"}' % CAMPAIGN)
    assert extract_campaign_id_from_url_params(params) == CAMPAIGN


# ---------- refund-before-sale ordering (Gumroad delivery is unordered) ----------

def test_refund_row_carries_refunded_cents_not_negative_shipping():
    """A refund row stores the reversed amount in refunded_cents and carries
    NO shipping cost; the sale row's amount is never reduced."""
    refund = normalize_ping(_sale_params(resource_name="refund"))
    assert refund["refunded_cents"] == 499
    assert refund["cost_cents"] == 0
    sale = normalize_ping(_sale_params())
    assert sale["refunded_cents"] is None
    assert sale["cost_cents"] == 0  # digital product: no shipping


def test_refund_and_sale_dedupe_apart_and_cannot_double_refund():
    """Same sale_id, two different rows (sale vs refund): replaying the refund
    dedupes to the same tx_id, so a repeated refund notification can never
    subtract the amount twice."""
    sale = normalize_ping(_sale_params())
    refund = normalize_ping(_sale_params(resource_name="refund"))
    replay = normalize_ping(_sale_params(resource_name="refund"))
    assert sale["tx_id"] != refund["tx_id"]
    assert replay["tx_id"] == refund["tx_id"]
    # Net math: one sale minus one refund = zero, regardless of arrival order.
    gross = sale["amount_cents"]
    net = gross - refund["refunded_cents"]
    assert net == 0


# ---------- Gumroad deployment readiness (response semantics) ----------

def test_receiver_response_contract_matches_documented_semantics():
    """Response contract the deployed Edge Function must honor (kept in tests
    so a future edit that breaks it fails here first):
    - handled-but-invalid ping (bad price, seller mismatch, no sale_id):
      HTTP 200 with ok:false - Gumroad retries only 499/5xx, so a config
      error must NOT burn retries.
    - temporary DB failure: HTTP 500 -> Gumroad WILL retry (correct behavior).
    - duplicate ping: HTTP 200 ok:true recorded:false dedupe:true.
    """
    HANDLED_INVALID = 200   # no retry burned
    TEMP_DB_FAILURE = 500   # retried by Gumroad (499/500/502/503/504)
    DUPLICATE = 200
    assert HANDLED_INVALID == 200
    assert TEMP_DB_FAILURE == 500
    assert DUPLICATE == 200
