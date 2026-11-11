import json
from bs4 import BeautifulSoup

html_graph = '''<script type="application/ld+json">
{"@graph": [{"@type": "Product", "name": "G", "description": "xx", "offers": {"price": 7}}]}</script>'''
soup = BeautifulSoup(html_graph, "html.parser")
scripts = soup.find_all("script", type="application/ld+json")
print("scripts:", scripts)
data = json.loads(scripts[0].string or scripts[0].get_text() or "")
print("data:", data)
nodes = data.get("@graph", []) if isinstance(data, dict) and "@graph" in data else (
    data if isinstance(data, list) else [data])
print("nodes:", nodes)
