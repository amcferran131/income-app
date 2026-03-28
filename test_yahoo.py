import yfinance as yf
import requests

print("--- Yahoo Connectivity Test ---")
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
session = requests.Session()
session.headers.update(headers)

try:
    print("Testing MSFT (Microsoft)...")
    msft = yf.Ticker("MSFT", session=session)
    price = msft.fast_info.last_price
    print(f"CONNECTION SUCCESS! Current Price: ${price}")
    
    print("Checking Dividends...")
    divs = msft.dividends
    if not divs.empty:
        print("DIVIDEND SUCCESS! Data received.")
    else:
        print("PARTIAL SUCCESS: Connected, but no dividend data found.")

except Exception as e:
    print(f"CONNECTION FAILED.")
    print(f"Error Message: {e}")

input("\nPress Enter to close...")