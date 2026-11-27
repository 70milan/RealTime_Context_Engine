"""Local API auth: only the Electron app that started this backend may call it."""
import os
from typing import Optional

# =============================================================================
# LOCAL API AUTH
# =============================================================================
# Any web page open in the user's browser can send requests to 127.0.0.1:5050.
# Electron generates a random per-launch secret and passes it in WINHOST_TOKEN;
# every request must echo it back (X-App-Token header, or ?token= for the
# WebSocket, which can't carry custom headers). A web page never learns it.
# Unset (dev: `uvicorn main:app` run by hand) -> auth disabled with a warning.
import hmac

APP_TOKEN = os.getenv("WINHOST_TOKEN", "")
ALLOWED_HOSTS = {"127.0.0.1:5050", "localhost:5050"}  # blocks DNS-rebinding
if not APP_TOKEN:
    print("[SECURITY WARNING] WINHOST_TOKEN not set - local API auth DISABLED (dev mode)")

def _token_ok(supplied: Optional[str]) -> bool:
    if not APP_TOKEN:
        return True
    return bool(supplied) and hmac.compare_digest(supplied, APP_TOKEN)

