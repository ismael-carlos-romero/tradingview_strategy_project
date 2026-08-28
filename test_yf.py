import yfinance as yf
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

ticker = "SPY"
try:
    print(f"Testing download for {ticker} using custom session with Chrome User-Agent...")
    data = yf.download(ticker, period="5d", interval="1h", session=session)
    print("Download outcome:")
    print(data)
except Exception as e:
    print(f"Error occurred: {e}")
