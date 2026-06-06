import pandas as pd
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
tables = pd.read_html("https://en.wikipedia.org/wiki/2026_FIFA_World_Cup")
print(f"Found {len(tables)} tables")
for i, t in enumerate(tables):
    if "Match" in t.columns or "Date" in t.columns or "Venue" in t.columns:
        print(f"Table {i}: {t.columns.tolist()[:5]}")
        print(t.head(2))
