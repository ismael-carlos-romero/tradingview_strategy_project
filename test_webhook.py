import requests
import json

webhook_url = "https://script.google.com/macros/s/AKfycbxbLkV8YMCxcQjI9GVtxXx56WtJO2jH-54k9M8bylct9v2uhf7CZI9ewIGFOnI05QPE/exec"

test_data = {
    "action": "bulk_import",
    "trades": [
        {
            "status": "Test_Open",
            "buyDate": "2026-06-19 12:00:00",
            "sellDate": "",
            "ticker": "TEST",
            "type": "CALL",
            "strike": 100,
            "expiry": "2026-06-26",
            "quantity": 1,
            "buyPrice": 1.50,
            "sellPrice": 0.0,
            "strategy": "Test Bulk Import"
        }
    ]
}

print("Enviando POST a webhook...")
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    r = requests.post(webhook_url, json=test_data, headers={"Content-Type": "text/plain"}, verify=False)
    print("Status Code:", r.status_code)
    print("Response text:", r.text)
except Exception as e:
    print("Error:", e)
