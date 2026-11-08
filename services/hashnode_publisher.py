"""Publishes articles to Hashnode via its free GraphQL API.

Tries both accepted Authorization header styles and prints the server's
exact answer whenever something fails, so failures are never silent.
"""
import requests

_GQL = "https://gql.hashnode.com"


def _post(payload: dict, pat: str):
    """POST to the GraphQL API. Returns (json_dict, error_string)."""
    last = "no attempt made"
    for auth in (pat, f"Bearer {pat}"):
        try:
            r = requests.post(
                _GQL,
                json=payload,
                headers={"Authorization": auth, "Content-Type": "application/json"},
                timeout=20,
            )
        except Exception as e:
            last = f"network error: {e}"
            continue
        if r.status_code == 200:
            try:
                return r.json(), None
            except ValueError:
                last = f"non-JSON reply: HTTP {r.status_code} body={r.text[:200]!r}"
                continue
        last = f"HTTP {r.status_code}: {r.text[:200]!r}"
        if r.status_code not in (401, 403):
            break
    return None, last


def publish_to_hashnode(headline: str, body: str, campaign_url: str, pat: str) -> bool:
    if not pat:
        return False

    data, err = _post({"query": "{ me { publications(first: 1) { edges { node { id } } } } }"}, pat)
    if err:
        print(f"Hashnode publications query failed -> {err}")
        return False
    if "errors" in data:
        print(f"Hashnode publications query errors -> {data['errors']}")
        return False
    edges = data.get("data", {}).get("me", {}).get("publications", {}).get("edges", [])
    if not edges:
        print("Hashnode: no publication found. Publish one post manually at hashnode.com to initialize your blog.")
        return False
    pub_id = edges[0]["node"]["id"]

    mutation = "mutation ($input: CreatePostInput!) { createPost(input: $input) { post { id } } }"
    variables = {
        "input": {
            "publicationId": pub_id,
            "title": headline[:120],
            "contentMarkdown": body + f"\n\n[Read the full page here]({campaign_url})",
            "tags": [{"slug": "finance"}, {"slug": "money"}, {"slug": "productivity"}],
            "canonicalUrl": campaign_url,
            "draft": False,
        }
    }
    data2, err2 = _post({"query": mutation, "variables": variables}, pat)
    if err2:
        print(f"Hashnode createPost failed -> {err2}")
        return False
    if "errors" in data2:
        print(f"Hashnode createPost errors -> {data2['errors']}")
        return False
    return True