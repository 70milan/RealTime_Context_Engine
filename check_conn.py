import requests
try:
    resp = requests.get("http://127.0.0.1:5050/profile")
    print(f"STATUS: {resp.status_code}")
    print(f"BODY: {resp.text}")
except Exception as e:
    print(f"ERROR: {e}")
