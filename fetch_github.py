import requests
import json

headers = {"Accept": "application/vnd.github.v3+json"}
url = "https://api.github.com/search/code?q=match+schedule+2026+world+cup+extension:json"
resp = requests.get(url, headers=headers)
data = resp.json()

if "items" in data:
    for item in data["items"][:5]:
        print(item["html_url"])
