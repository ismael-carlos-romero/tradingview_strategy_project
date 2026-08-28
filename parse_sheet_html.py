import re
import json

filepath = r"C:\Users\Ismael Romero\.gemini\antigravity\brain\63c80efb-e588-4e13-9a8c-2b4636f0c6a2\.system_generated\steps\410\content.md"

with open(filepath, "r", encoding="utf-8") as f:
    html = f.read()

# Let's search for sheet names or document title
title_match = re.search(r"<title>(.*?)</title>", html)
if title_match:
    print("Document Title:", title_match.group(1))

# Search for the WIZ_global_data or some other JSON structure containing sheet names
# Sheets metadata is often in a JSON array inside a script tag
# Look for sheetNames or specific names we know
for sheet_name in ["Simulacion-Uchart", "Ucharts Compuesto", "UCharts Compuesto", "Monitoreo en Vivo", "UCHARTS-NUEVO"]:
    if sheet_name in html:
        print(f"Found Sheet Name: {sheet_name}")

# Let's inspect the gid=1334901184 mapping in the HTML
gid_matches = re.findall(r"gid=(\d+)", html)
print("Unique GIDs found:", set(gid_matches))
