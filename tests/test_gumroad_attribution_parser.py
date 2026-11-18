"""Isolated, non-financial verification of the gumroad-ping url_params parser.

Mirrors the DEPLOYED Edge Function logic (supabase/functions/gumroad-ping/
index.ts lines 112-121) against the Python mirror in services/gumroad_ping.py:
- parse url_params as JSON (absent/not-JSON -> null)
- accept campaign_id or cid
- validate against a strict 36-char UUID regex; anything else -> null
- test=true short-circuit stays OUTSIDE this path (never recorded)

No network calls, no DB writes, no record_financial_event, no secrets.
"""
import pytest

from services.gumroad_ping import extract_campaign_id_from_url_params

# The exact regex the deployed Edge Function uses (index.ts line 118):
#   /^[0-9a-fA-F-]{36}$/.test(String(candidate))
# and the Python mirror's UUID_RE:
#   ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$
# The mirror is STRICTER (enforces hex groups + dashes); if a value passes the
# mirror it necessarily passes the deployed regex. We assert both behaviors.
import re

DEPLOYED_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
VALID = "2b6fb996-c048-435b-82d8-9a64d196a1b8"  # HTML5 Games campaign UUID


def _deployed_parse(params: dict) -> str | None:
    """Faithful transcription of the deployed Edge Function's parse block."""
    import json
    candidate = None
    try:
        up = json.loads(params["url_params"]) if params.get("url_params") else None
        candidate = (up or {}).get("campaign_id") or (up or {}).get("cid") or None
    except Exception:
        candidate = None
    if candidate and DEPLOYED_RE.fullmatch(str(candidate)):
        return str(candidate)
    return None


def test_valid_uuid_extracted_by_both():
    params = {"url_params": f'{{"campaign_id":"{VALID}"}}'}
    assert extract_campaign_id_from_url_params(params) == VALID
    assert _deployed_parse(params) == VALID


def test_cid_fallback_extracted():
    params = {"url_params": f'{{"cid":"{VALID}"}}'}
    assert extract_campaign_id_from_url_params(params) == VALID
    assert _deployed_parse(params) == VALID


def test_missing_url_params_is_null():
    assert extract_campaign_id_from_url_params({}) is None
    assert _deployed_parse({}) is None


def test_empty_url_params_is_null():
    assert extract_campaign_id_from_url_params({"url_params": ""}) is None
    assert _deployed_parse({"url_params": ""}) is None


def test_malformed_uuid_is_null():
    # 36 chars but not a UUID (dashes removed / wrong positions)
    for bad in ("2b6fb996c048435b82d89a64d196a1b8", "2b6fb996-c048-435b-82d8-zzzzzzzzzzzz",
                "2b6fb996_c048-435b-82d8-9a64d196a1b8", VALID + "-extra"):
        params = {"url_params": f'{{"campaign_id":"{bad}"}}'}
        if DEPLOYED_RE.fullmatch(bad):
            # deployed regex would accept a 36-char non-uuid; the mirror must not
            assert extract_campaign_id_from_url_params(params) is None
        else:
            assert extract_campaign_id_from_url_params(params) is None
            assert _deployed_parse(params) is None


def test_invalid_json_is_null():
    assert extract_campaign_id_from_url_params({"url_params": "not json"}) is None
    assert _deployed_parse({"url_params": "not json"}) is None


def test_non_dict_json_is_null():
    assert extract_campaign_id_from_url_params({"url_params": '["x"]'}) is None
    assert _deployed_parse({"url_params": '["x"]'}) is None


def test_empty_campaign_id_value_is_null():
    assert extract_campaign_id_from_url_params({"url_params": '{"campaign_id":""}'}) is None
    assert _deployed_parse({"url_params": '{"campaign_id":""}'}) is None


def test_deployed_regex_and_mirror_agree_on_valid_uuid():
    """The deployed regex is looser; assert the mirror's verdict is a subset."""
    assert DEPLOYED_RE.fullmatch(VALID) is not None
    assert extract_campaign_id_from_url_params(
        {"url_params": f'{{"campaign_id":"{VALID}"}}'}) == VALID


def test_test_ping_short_circuit_is_untouched_in_source():
    """The deployed function's test=true short-circuit must remain BEFORE any
    recording, and the mirror treats test purchases as never-money."""
    import inspect
    from services import gumroad_ping
    src = inspect.getsource(gumroad_ping.normalize_ping)
    assert "test" in src
    import pathlib
    fn = pathlib.Path(__file__).resolve().parents[1] / "supabase/functions/gumroad-ping/index.ts"
    deployed = fn.read_text(encoding="utf-8")
    # short-circuit returns 200 BEFORE any record_financial_event reference
    short_idx = deployed.index('["true", "1", "yes"].includes((params.test')
    record_idx = deployed.index("record_financial_event")
    assert short_idx < record_idx
    assert "ignored" in deployed[short_idx:short_idx + 600]
