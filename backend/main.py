# backend/main.py - Interview Assistant backend: builds the FastAPI app from engine/
print("[STARTUP] Initializing Interview Assistant Backend...")
import os
import threading
from typing import Optional

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from engine import api_review, api_sessions, api_settings, answers, practice, transcription
from engine.security import ALLOWED_HOSTS, _token_ok
from engine.usage import get_encoding
from engine.user_profile import _profile, save_profile, get_api_key, get_async_client

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lightweight liveness probe — lets the Electron launcher show the window the
# moment the backend is actually ready, instead of waiting a fixed delay.
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.middleware("http")
async def require_app_token(request: Request, call_next):
    # CORS preflights and the readiness probe carry no data and stay open
    if request.method == "OPTIONS" or request.url.path == "/health":
        return await call_next(request)
    if request.headers.get("host", "") not in ALLOWED_HOSTS:
        return JSONResponse({"error": "forbidden host"}, status_code=403)
    if not _token_ok(request.headers.get("x-app-token")):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

# Debug middleware to log raw requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if request.url.path == "/ai":
        body = await request.body()
        print(f"\n[RAW REQUEST] /ai received {len(body)} bytes")
        try:
            data = json.loads(body)
            print(f"[RAW REQUEST] Keys: {list(data.keys())}")
            for k, v in data.items():
                if k == 'screenshot':
                    print(f"  {k}: <{len(str(v))} chars>")
                elif isinstance(v, str) and len(v) > 100:
                    print(f"  {k}: {v[:100]}...")
                else:
                    print(f"  {k}: {v}")
        except Exception as e:
            print(f"[RAW REQUEST] Failed to parse JSON: {e}")
            print(f"[RAW REQUEST] Body preview: {body[:500]}")
    response = await call_next(request)
    return response

for module in (api_settings, api_sessions, api_review, practice, answers, transcription):
    app.include_router(module.router)


# ── Startup ─────────────────────────────────────────────────────────────────
# The app is free: older versions kept a license key and demo timers in the
# profile; they are dropped once so nothing can ever limit a session.
_LEGACY_LICENSE_FIELDS = ('license_key', 'demo_started_at', 'last_demo_end_time')
if any(k in _profile() for k in _LEGACY_LICENSE_FIELDS):
    for _k in _LEGACY_LICENSE_FIELDS:
        _profile().pop(_k, None)
    try:
        save_profile(_profile())
        print("[STARTUP] Removed old license / demo data from the profile")
    except Exception as e:
        print(f"[STARTUP] Could not clean the profile: {e}")

def _warm_up():
    """Runs in the background so /health answers as soon as FastAPI is up: loads
    openai, tiktoken and the client so the first answer doesn't stall the server."""
    try:
        from openai import AsyncOpenAI
        # Touching .chat.completions triggers the SDK's lazy ~1.3 s resource import
        AsyncOpenAI(api_key="sk-warmup").chat.completions
        get_encoding()
        if get_api_key():
            get_async_client().chat.completions
    except Exception as e:
        print(f"[STARTUP] Warm-up skipped: {e}")

threading.Thread(target=_warm_up, daemon=True, name="warm-up").start()


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("Interview Assistant - Windows Runtime Host")
    print("API running on: http://localhost:5050")
    print("="*60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=5050, log_level="info", use_colors=False)
