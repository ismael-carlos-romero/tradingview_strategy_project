filepath = r"C:\Users\Ismael Romero\.gemini\antigravity\brain\63c80efb-e588-4e13-9a8c-2b4636f0c6a2\.system_generated\steps\519\content.md"

with open(filepath, "r", encoding="utf-8") as f:
    html = f.read()

if "TEST" in html:
    print("SUCCESS: Found 'TEST' in the spreadsheet HTML!")
    # Find some characters around it
    idx = html.index("TEST")
    print(html[idx-100:idx+150])
else:
    print("FAILED: Did not find 'TEST' in the spreadsheet HTML.")
