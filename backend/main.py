# backend/main.py
print("[STARTUP] Initializing Interview Assistant Backend...")
from fastapi import FastAPI, WebSocket, Request

from fastapi.responses import StreamingResponse
import os
import sys
import io

import json
import re
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from openai import AsyncOpenAI

# Token counting for cost estimation (Lazy Loaded)
_encoding = None

def get_encoding():
    global _encoding
    if _encoding is None:
        try:
            import tiktoken
            _encoding = tiktoken.encoding_for_model("gpt-4o")
            print("[STARTUP] tiktoken loaded - accurate token counting enabled")
        except:
            _encoding = "fallback"
            print("[STARTUP WARNING] tiktoken not available - cost estimation will be APPROXIMATE (len/4)")
    return _encoding


# Session usage tracking
session_usage = {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_cost": 0.0,          # AI answers + transcription
    "request_count": 0,
    "ai_cost": 0.0,
    "transcription_seconds": 0.0,
    "transcription_cost": 0.0
}

# OpenAI prices per 1M tokens (platform.openai.com/docs/pricing, checked Nov 2026).
# "cached" is the rate for prompt tokens OpenAI served from its prompt cache.
PRICING = {
    "gpt-3.5-turbo": {"input": 0.50, "cached": 0.50, "output": 1.50},
    "gpt-4o-mini": {"input": 0.15, "cached": 0.075, "output": 0.60},
    "gpt-4o": {"input": 2.50, "cached": 1.25, "output": 10.00},
    "gpt-5-nano": {"input": 0.05, "cached": 0.005, "output": 0.40},
    "gpt-5-mini": {"input": 0.25, "cached": 0.025, "output": 2.00},
}

# License State (Backend Enforcement)
# Default to unlicensed until validation
is_licensed_backend = False
import threading
_license_checked = threading.Event()  # set once check_saved_license() has run
DEMO_LIMIT_MS = 12 * 60 * 1000
DEMO_COOLDOWN_MS = 47 * 60 * 1000



# Available models for text-only responses (user can select)
AVAILABLE_TEXT_MODELS = {
    "gpt-3.5-turbo": {"name": "GPT-3.5 Turbo", "speed": "Fastest", "cost": "Cheapest", "accuracy": "Good", "desc": "Quick text answers"},
    "gpt-4o-mini": {"name": "GPT-4o Mini", "speed": "Fast", "cost": "Cheap", "accuracy": "Better", "desc": "Balanced option"},
    "gpt-4o": {"name": "GPT-4o", "speed": "Medium", "cost": "Moderate", "accuracy": "Great", "desc": "Complex questions"},
    "gpt-5-nano": {"name": "ChatGPT 5 Nano", "speed": "Ultrasonic", "cost": "Cheapest", "accuracy": "Decent", "desc": "Lightweight tasks"},
    "gpt-5-mini": {"name": "ChatGPT 5 Mini", "speed": "Blistering", "cost": "Cheap", "accuracy": "Solid", "desc": "Day-to-day tasks"}
}

DEFAULT_TEXT_MODEL = "gpt-4o-mini"

def count_tokens(text: str) -> int:
    """Count tokens in text"""
    enc = get_encoding()
    if enc and enc != "fallback":
        return len(enc.encode(text))
    return len(text) // 4  # Rough estimate


def estimate_image_tokens(base64_data: str, model: str = "gpt-4o") -> int:
    """Estimate tokens for an image based on base64 data size.
    GPT-4o uses ~255 tokens per 512x512 tile.
    We estimate image dimensions from base64 size and calculate tiles.
    """
    try:
        # Remove data URL prefix if present
        if "base64," in base64_data:
            base64_data = base64_data.split("base64,")[1]
        
        # Estimate image size from base64 length
        # Base64 is ~4/3 of original size, JPEG compression is ~10:1
        byte_size = len(base64_data) * 3 // 4
        estimated_pixels = byte_size * 10  # Rough decompression estimate
        
        # Estimate dimensions (assume roughly square)
        import math
        side = int(math.sqrt(estimated_pixels))
        
        # GPT-4o: 512x512 tiles, ~255 tokens per tile + 85 base tokens
        tiles_x = max(1, (side + 511) // 512)
        tiles_y = max(1, (side + 511) // 512)
        total_tiles = tiles_x * tiles_y
        
        # Base 85 tokens + 255 per tile (GPT-4o vision formula)
        image_tokens = 85 + (255 * total_tiles)
        
        print(f"[IMAGE TOKENS] Estimated {image_tokens} tokens for ~{side}x{side} image ({total_tiles} tiles)")
        return image_tokens
    except Exception as e:
        print(f"[IMAGE TOKENS] Error estimating: {e}, using default 500")
        return 500  # Safe default for a medium image

def calculate_cost(input_tokens: int, output_tokens: int, model: str = "gpt-4o", image_tokens: int = 0, cached_tokens: int = 0) -> float:
    """Cost in dollars. input_tokens includes cached_tokens, the way OpenAI reports usage."""
    pricing = PRICING.get(model, PRICING["gpt-4o"])
    fresh = max(0, input_tokens + image_tokens - cached_tokens)
    return (fresh * pricing["input"] + cached_tokens * pricing["cached"] + output_tokens * pricing["output"]) / 1_000_000

def update_usage(input_tokens: int, output_tokens: int, model: str = "gpt-4o-mini", image_tokens: int = 0, cached_tokens: int = 0) -> float:
    """Add one model call to the session totals; returns that call's cost"""
    global session_usage
    session_usage["input_tokens"] += input_tokens + image_tokens
    session_usage["output_tokens"] += output_tokens
    cost = calculate_cost(input_tokens, output_tokens, model, image_tokens, cached_tokens)
    session_usage["total_cost"] += cost
    session_usage["ai_cost"] = session_usage.get("ai_cost", 0.0) + cost
    session_usage["request_count"] += 1
    print(f"[USAGE] +${cost:.5f} {model} ({input_tokens} in, {cached_tokens} cached, {output_tokens} out) | session ${session_usage['total_cost']:.4f}")
    return cost

def track_completion_usage(usage, model: str) -> float:
    """update_usage from an OpenAI usage object (non-streamed calls)"""
    if not usage:
        return 0.0
    details = getattr(usage, 'prompt_tokens_details', None)
    cached = (getattr(details, 'cached_tokens', 0) or 0) if details else 0
    return update_usage(usage.prompt_tokens, usage.completion_tokens, model, cached_tokens=cached)

# Fix Unicode encoding for Windows console (prevents charmap errors with special characters)
# if sys.platform == 'win32':
#     try:
#         sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
#         sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
#     except (AttributeError, Exception):
#         pass # Fallback to default if buffer not accessible


app = FastAPI()

# Determine base directory for data storage (persists across updates)
if getattr(sys, 'frozen', False):
    # Running as compiled executable - store data in AppData to survive updates
    # e.g., C:\Users\<user>\AppData\Roaming\jobandit\backend
    app_data = os.getenv('APPDATA')
    if app_data:
        BASE_DIR = Path(app_data) / "jobandit" / "backend"
        BASE_DIR.mkdir(parents=True, exist_ok=True)
    else:
        # Fallback if APPDATA not found (rare)
        BASE_DIR = Path(sys.executable).parent
else:
    # Running as script - store locally
    BASE_DIR = Path(__file__).parent

# =============================================================================
# KEY FILE CONFIGURATION (Must be after BASE_DIR)
# =============================================================================
PUBLIC_KEY_NAME = "public_key.pem"
PRIVATE_KEY_NAME = "private_key.pem"
# Use absolute paths for key files (essential for frozen EXEs)
PUBLIC_KEY_FILE = BASE_DIR / PUBLIC_KEY_NAME
PRIVATE_KEY_FILE = BASE_DIR / PRIVATE_KEY_NAME

# Allow the Electron frontend and local testing to call the API
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

# =============================================================================
# LOCAL API AUTH
# =============================================================================
# Any web page open in the user's browser can send requests to 127.0.0.1:5050.
# Electron generates a random per-launch secret and passes it in WINHOST_TOKEN;
# every request must echo it back (X-App-Token header, or ?token= for the
# WebSocket, which can't carry custom headers). A web page never learns it.
# Unset (dev: `uvicorn main:app` run by hand) -> auth disabled with a warning.
import hmac
from fastapi.responses import JSONResponse

APP_TOKEN = os.getenv("WINHOST_TOKEN", "")
ALLOWED_HOSTS = {"127.0.0.1:5050", "localhost:5050"}  # blocks DNS-rebinding
if not APP_TOKEN:
    print("[SECURITY WARNING] WINHOST_TOKEN not set - local API auth DISABLED (dev mode)")

def _token_ok(supplied: Optional[str]) -> bool:
    if not APP_TOKEN:
        return True
    return bool(supplied) and hmac.compare_digest(supplied, APP_TOKEN)

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

def get_api_key():
    """Get API key from user profile - checks memory cache first, then disk"""
    global profile_cache
    # 1. Check in-memory cache first (fastest)
    if isinstance(profile_cache, dict) and profile_cache.get('openai_api_key'):
        key = profile_cache['openai_api_key'].strip()
        if key.startswith("sk-") and not key.endswith("KiwA"):
            return key
            
    # 2. Fall back to disk if not in memory
    disk_profile = load_profile()
    if isinstance(disk_profile, dict) and disk_profile.get('openai_api_key'):
        key = disk_profile['openai_api_key'].strip()
        if key.startswith("sk-") and not key.endswith("KiwA"):
            print(f"[get_api_key] Restored valid key from disk: {key[:8]}...{key[-4:]}")
            if not isinstance(profile_cache, dict):
                profile_cache = {}
            profile_cache['openai_api_key'] = key
            return key
            
    # 3. Fall back to environment variable as last resort
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        print(f"[get_api_key] Falling back to environment variable: {env_key[:8]}...")
        return env_key.strip()
        
    return None

# One AsyncOpenAI client per API key: the sync client blocked the event loop for
# the whole streamed answer, stalling live transcription and every other request.
# openai is imported lazily: it is ~2.5 s of startup, and the warm-up thread
# loads it in the background right after the server starts listening.
_async_clients: Dict[str, "AsyncOpenAI"] = {}

def get_async_client(api_key: Optional[str] = None) -> "AsyncOpenAI":
    from openai import AsyncOpenAI
    key = api_key or get_api_key()
    client = _async_clients.get(key)
    if client is None:
        client = AsyncOpenAI(api_key=key)
        _async_clients.clear()  # key changed - drop the old client
        _async_clients[key] = client
    return client

# Streaming transcription model: emits word-level deltas while the person is still
# talking (whisper-1 only returns text once the utterance ends). whisper-1 stays as
# the fallback for API keys/projects that don't have access to it.
TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
FALLBACK_TRANSCRIBE_MODEL = "whisper-1"
# OpenAI's published per-minute estimates for streamed audio (24 kHz PCM16 = 48000 bytes/s)
TRANSCRIBE_PRICE_PER_MIN = {"gpt-4o-mini-transcribe": 0.003, "whisper-1": 0.006}
PCM_BYTES_PER_SEC = 48000


def _add_transcription_usage(n_bytes: int, model: str):
    secs = n_bytes / PCM_BYTES_PER_SEC
    cost = secs / 60 * TRANSCRIBE_PRICE_PER_MIN.get(model, 0.006)
    session_usage["transcription_seconds"] = session_usage.get("transcription_seconds", 0.0) + secs
    session_usage["transcription_cost"] = session_usage.get("transcription_cost", 0.0) + cost
    session_usage["total_cost"] += cost


def _openai_error_message(err: dict) -> str:
    """User-facing text for a Realtime error event."""
    code = (err.get("code") or "")
    msg = err.get("message", "Unknown OpenAI error")
    if code == "insufficient_quota" or "quota" in msg.lower():
        return "OUT_OF_CREDITS: Your OpenAI account is out of credits."
    return msg


def _transcription_session(model: str, source: str, role: str) -> dict:
    # No transcription "prompt": gpt-4o-mini-transcribe repeats it back as a
    # transcript when it hears silence or room noise.
    transcription = {"model": model}
    audio_input = {
        "format": {"type": "audio/pcm", "rate": 24000},
        "transcription": transcription,
        "turn_detection": {
            "type": "server_vad",
            # The mic hears keyboard, breathing and speaker bleed: ask for clearer speech
            "threshold": 0.6 if source == "mic" else 0.45,
            "prefix_padding_ms": 200,
            "silence_duration_ms": 350,
        },
    }
    if source == "mic":
        audio_input["noise_reduction"] = {"type": "near_field"}
    return {"type": "session.update", "session": {"type": "transcription", "audio": {"input": audio_input}}}


@app.websocket("/realtime")
async def realtime(ws: WebSocket):
    # WebSockets bypass CORS and HTTP middleware entirely - check Host + token here
    if ws.headers.get("host", "") not in ALLOWED_HOSTS or not _token_ok(ws.query_params.get("token")):
        await ws.close(code=1008)
        return
    await ws.accept()

    # "system" = the other side of the call (interviewer), "mic" = the user
    source = ws.query_params.get("source", "system")
    if source not in ("system", "mic"):
        source = "system"
    tag = f"[WS:{source}]"

    access_allowed = check_access_allowed()
    if not access_allowed:
        print(f"{tag} Access denied (demo expired or unlicensed)")
        await ws.send_json({"type": "error", "message": "Demo expired. Please purchase a license to continue."})
        await ws.close()
        return

    api_key = get_api_key()

    # GA Realtime transcription session. The Beta Realtime API was removed
    # ("Realtime Beta API no longer supported" / close 4000); GA drops the
    # OpenAI-Beta header and uses the ?intent=transcription endpoint.
    url = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    if not api_key:
        print(f"{tag} ERROR: API key not found in profile or environment!")
        await ws.close(code=1008, reason="Missing API Key")
        return

    role = ""
    if isinstance(profile_cache, dict):
        role = (profile_cache.get("target_role") or "").strip()

    print(f"{tag} Connecting to OpenAI at {url}...")
    try:
        async with websockets.connect(url, additional_headers=headers) as openai_ws:
            model = TRANSCRIBE_MODEL
            print(f"{tag} Connected to OpenAI Realtime API (model {model})")
            # GA transcription schema: audio config is nested under session.audio.input.
            # The client streams 24kHz mono PCM16; server VAD segments each utterance.
            await openai_ws.send(json.dumps(_transcription_session(model, source, role)))

            upstream_closed = {"code": None, "reason": ""}
            client_gone = False

            async def receive_from_client():
                nonlocal client_gone
                try:
                    while True:
                        message = await ws.receive()
                        if message.get("type") == "websocket.disconnect":
                            client_gone = True
                            break

                        if message.get("bytes") is not None:
                            import base64
                            _add_transcription_usage(len(message["bytes"]), model)
                            audio_b64 = base64.b64encode(message["bytes"]).decode()
                        else:
                            audio_b64 = message.get("text", "")

                        event = {
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64
                        }
                        await openai_ws.send(json.dumps(event))
                except WebSocketDisconnect:
                    client_gone = True
                except websockets.exceptions.ConnectionClosed:
                    pass  # upstream went away; receive_from_openai records why
                except Exception as e:
                    print(f"{tag} [receive_from_client] Error: {e}")
                finally:
                    # Client left: close upstream so receive_from_openai ends too
                    try:
                        await openai_ws.close()
                    except Exception:
                        pass

            async def receive_from_openai():
                nonlocal model
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        etype = event.get("type", "")
                        item_id = event.get("item_id", "")

                        if etype == "conversation.item.input_audio_transcription.delta":
                            delta = event.get("delta", "")
                            if delta:
                                await ws.send_json({"type": "transcript_delta", "item_id": item_id, "text": delta})

                        elif etype == "conversation.item.input_audio_transcription.completed":
                            transcript = event.get("transcript", "").strip()
                            print(f"{tag} [TRANSCRIPT] {transcript}")
                            await ws.send_json({"type": "transcript_final", "item_id": item_id, "text": transcript})

                        elif etype == "conversation.item.input_audio_transcription.failed":
                            print(f"{tag} [TRANSCRIPT FAILED] {event.get('error')}")
                            await ws.send_json({"type": "transcript_final", "item_id": item_id, "text": ""})

                        elif etype == "input_audio_buffer.speech_started":
                            await ws.send_json({"type": "speech_started", "item_id": item_id})

                        elif etype == "input_audio_buffer.speech_stopped":
                            await ws.send_json({"type": "speech_stopped", "item_id": item_id})

                        elif etype == "error":
                            err = event.get("error", {}) or {}
                            msg = _openai_error_message(err)
                            print(f"{tag} [OPENAI ERROR] {err.get('code')} - {err.get('message')}")
                            # No access to the streaming model: fall back to whisper-1
                            if model != FALLBACK_TRANSCRIBE_MODEL and (
                                "model" in (err.get("param") or "") or "model" in msg.lower()
                            ):
                                model = FALLBACK_TRANSCRIBE_MODEL
                                print(f"{tag} Falling back to {model}")
                                await openai_ws.send(json.dumps(_transcription_session(model, source, role)))
                                continue
                            await ws.send_json({"type": "error", "message": msg})

                    upstream_closed["code"] = openai_ws.close_code
                    upstream_closed["reason"] = openai_ws.close_reason or ""
                except websockets.exceptions.ConnectionClosed as e:
                    upstream_closed["code"], upstream_closed["reason"] = e.code, e.reason or ""
                except Exception as e:
                    upstream_closed["code"], upstream_closed["reason"] = -1, str(e)[:80]
                    print(f"{tag} [receive_from_openai] Exception: {e}")
                finally:
                    # Unblock receive_from_client's pending ws.receive() if the client is still there
                    if not client_gone:
                        upstream_closed["told_client"] = True
                        try:
                            await ws.close(code=4001, reason=f"upstream {upstream_closed['code']} {upstream_closed['reason']}"[:120])
                        except Exception:
                            pass

            await asyncio.gather(receive_from_client(), receive_from_openai())
            if upstream_closed.get("told_client"):
                print(f"{tag} OpenAI connection ended: {upstream_closed['code']} {upstream_closed['reason']} (client told to reconnect)")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"{tag} OpenAI Connection Closed: {e.code} {e.reason}")
        await ws.close(code=1011, reason=f"OpenAI Closed: {e.code}")
    except Exception as e:
        print(f"{tag} Connection error: {e}")
        # Try to send the error to the client before closing
        try:
            await ws.close(code=1011, reason=f"Upstream Error: {str(e)[:100]}")
        except:
            pass

from pydantic import BaseModel
from fastapi import File, UploadFile, Form
def _docx_document():
    try:
        from docx import Document
        return Document
    except ModuleNotFoundError:
        return None


def _docx_text(content: bytes) -> str:
    """Text of a .docx in document order, including tables (resumes often keep skills in one)."""
    from io import BytesIO
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(BytesIO(content))
    lines = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            text = Paragraph(child, doc).text.strip()
            if text:
                lines.append(text)
        elif tag == 'tbl':
            for row in Table(child, doc).rows:
                cells = []
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and text not in cells:  # merged cells repeat their text
                        cells.append(text)
                if cells:
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


class AIRequest(BaseModel):
    transcript: str = ""
    role: str = ""
    target_language: Optional[str] = None
    screenshot: Optional[str] = None
    job_description: Optional[str] = None
    save_to_context: Optional[bool] = True
    text_model: Optional[str] = None
    # Smart Interview: transcript is a speaker-labeled exchange (Interviewer / Me)
    smart_mode: Optional[bool] = False
    # What the session history should show as the question (Smart: just the
    # interviewer's question, not the full prompt sent to the model)
    display_question: Optional[str] = None

    model_config = {"extra": "ignore"}


@app.get('/models')
async def get_available_models():
    """Return available text models with metadata for UI display"""
    models = []
    for model_id, info in AVAILABLE_TEXT_MODELS.items():
        pricing = PRICING.get(model_id, {})
        models.append({
            "id": model_id,
            "name": info["name"],
            "speed": info["speed"],
            "cost": info["cost"],
            "accuracy": info["accuracy"],
            "description": info["desc"],
            "price_input": pricing.get("input", 0),
            "price_output": pricing.get("output", 0)
        })
    return {"models": models, "default": DEFAULT_TEXT_MODEL}


# Persistent profile support -------------------------------------------------
PROFILE_PATH = BASE_DIR / "user_profile.json"

# The OpenAI key is stored encrypted with Windows DPAPI (bound to this Windows
# user account) instead of plain text. In memory it is always 'openai_api_key';
# on disk it is 'openai_api_key_enc'. Old plain-text profiles are migrated on load.
import base64

def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if not fn(ctypes.byref(blob_in), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

def encrypt_secret(value: str) -> str:
    if sys.platform != 'win32':
        return value
    return base64.b64encode(_dpapi(value.encode('utf-8'), True)).decode('ascii')

def decrypt_secret(value: str) -> str:
    if sys.platform != 'win32':
        return value
    return _dpapi(base64.b64decode(value), False).decode('utf-8')

def load_profile() -> Dict[str, Any]:
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Error loading profile: {e}")
            return {}
        enc = data.pop('openai_api_key_enc', None)
        if enc:
            try:
                data['openai_api_key'] = decrypt_secret(enc)
            except Exception as e:
                print(f"[PROFILE] Could not decrypt API key (different Windows user?): {e}")
        elif data.get('openai_api_key'):
            try:
                save_profile(data)  # legacy plain-text key -> rewrite encrypted
                print("[PROFILE] Migrated plain-text API key to encrypted storage")
            except Exception:
                pass
        return data
    return {}

def save_profile(data: Dict[str, Any]):
    try:
        data = dict(data)
        key = data.pop('openai_api_key', None)
        if key:
            data['openai_api_key_enc'] = encrypt_secret(key)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        PROFILE_PATH.write_text(json_str, encoding="utf-8")
        print(f"[SAVE_PROFILE] Successfully wrote {len(json_str)} bytes to {PROFILE_PATH}")
    except Exception as e:
        print(f"[SAVE_PROFILE ERROR] Failed to save: {e}")
        raise  # Re-raise so caller knows it failed

profile_cache = load_profile()

# ============ CONVERSATION MEMORY ============
# Besides the session prompt, each answer carries:
#   - the last HISTORY_TURNS questions and answers verbatim (a follow-up like "optimize it" needs the code)
#   - one line per older question (what was asked, what you claimed), capped at MAX_NOTES, so later
#     answers stay consistent without the prompt growing for the whole interview
HISTORY_TURNS = 2
MAX_NOTES = 12
conversation_history = []   # [{"role": "user" | "assistant", "content": str}], at most HISTORY_TURNS pairs
conversation_notes = []     # ["Q: ... -> A: ..."], oldest first

# Bumped whenever the conversation is reset, so a note that finishes after the
# session ended can't leak into the next session.
_context_epoch = 0
_background_tasks = set()

def reset_conversation_context():
    global conversation_history, conversation_notes, _context_epoch
    conversation_history = []
    conversation_notes = []
    _context_epoch += 1

def record_turn(question: str, answer: str):
    """Remember a finished answer. The pair that ages out becomes a note in the background,
    so the client gets 'done' without waiting."""
    global conversation_history
    conversation_history = conversation_history + [{"role": "user", "content": question},
                                                   {"role": "assistant", "content": answer}]
    keep = HISTORY_TURNS * 2
    if len(conversation_history) > keep:
        evicted, conversation_history = conversation_history[:-keep], conversation_history[-keep:]
        task = asyncio.create_task(_note_in_background(evicted, _context_epoch))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

async def _note_in_background(turns: list, epoch: int):
    note = await note_for_turns(turns)
    if note and epoch == _context_epoch:
        conversation_notes.append(note)
        del conversation_notes[:-MAX_NOTES]

NOTE_INSTRUCTIONS = (
    "Write ONE line, at most 35 words, recording this interview exchange for the candidate's memory: "
    "'Q: <what was asked> -> A: <the specific facts the candidate stated: employer, tools, numbers, decisions; "
    "or the approach for a coding task>'. No other text."
)

async def note_for_turns(turns: list) -> str:
    """One-line note for evicted question/answer pairs (gpt-4o-mini, ~$0.0001)"""
    if not turns or not get_api_key():
        return ""
    text = "\n\n".join(f"{'QUESTION' if m['role'] == 'user' else 'CANDIDATE ANSWER'}: {m['content'][:1500]}" for m in turns)
    try:
        resp = await get_async_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": NOTE_INSTRUCTIONS}, {"role": "user", "content": text}],
            max_tokens=90,
            temperature=0.0,
        )
        track_completion_usage(resp.usage, "gpt-4o-mini")
        return " ".join((resp.choices[0].message.content or "").split())
    except Exception as e:
        print(f"[NOTES ERROR] {e}")
        return ""  # Non-fatal: this turn just isn't remembered

# ============ ACTIVE SESSION CONTEXT ============
# Everything an answer is built from, set when a session is created (/session/save) or
# resumed (/session/activate). Kept in memory: answers never read the profile from disk,
# and only the active session's resume, JD, brief and modes can reach the prompt.
CONTEXT_FIELDS = {
    'target_role': '', 'target_language': '', 'resume_text': '', 'job_description': '',
    'talking_points': '', 'is_esl': False, 'short_responses': False,  # short_responses = Cue Mode
}
active_context: Dict[str, Any] = {}

def set_active_context(session_name: str, data: Dict[str, Any], remember: bool = True):
    """Make a session the one answers are built from, with a fresh conversation memory"""
    global active_context, current_session_name
    active_context = {k: (data.get(k) or default) for k, default in CONTEXT_FIELDS.items()}
    current_session_name = session_name
    reset_conversation_context()
    invalidate_context_cache()
    if remember:
        # The profile only remembers WHICH session is active (to recover after a backend
        # restart); older versions copied the resume/JD/modes into it, which went stale
        p = _profile()
        for k in CONTEXT_FIELDS:
            p.pop(k, None)
        p['active_session'] = session_name
        save_profile(p)
    print(f"[CONTEXT] Active session '{session_name}': role={active_context['target_role']!r}, "
          f"brief={len(active_context['talking_points'])} chars, resume={len(active_context['resume_text'])} chars, "
          f"jd={len(active_context['job_description'])} chars, esl={active_context['is_esl']}, cue={active_context['short_responses']}")

def clear_active_context():
    global active_context, current_session_name
    active_context = {}
    current_session_name = None
    reset_conversation_context()
    invalidate_context_cache()
    p = _profile()
    if p.pop('active_session', None) is not None:
        save_profile(p)

def get_active_context() -> Dict[str, Any]:
    """The active session's context. If the backend restarted mid-session, recover it
    from the session it was serving."""
    if not active_context:
        name = _profile().get('active_session')
        if name:
            try:
                data = json.loads((safe_session_dir(name) / 'session.json').read_text(encoding='utf-8'))
                set_active_context(name, data, remember=False)
                print(f"[CONTEXT] Recovered active session '{name}' after restart")
            except Exception as e:
                print(f"[CONTEXT] Could not recover session '{name}': {e}")
    return active_context

# Answers that put a tool at the wrong job fall apart on the first follow-up question
TRUTHFULNESS_RULES = (
    "Only say you used a tool, platform or architecture at an employer if YOUR brief or resume lists it for that employer. "
    "If asked about something you used at a different job, say where (e.g. 'At Blue Cross I...'). "
    "If you have not used it, say so in one short sentence, then explain how you would approach it using related experience. "
    "Never invent layers, architectures, tools or numbers for any company: the interviewer will ask follow-ups about them."
)

ESL_RULES = (
    "ESL MODE: the candidate speaks English as a second language. One idea per sentence, short simple sentences, "
    "no idioms or figures of speech, no multi-clause sentences. Keep technical terms, with a few plain words of "
    "explanation the first time."
)

CUE_RULES = (
    "CUE MODE: the candidate speaks in their own words and only glances at your reply. Your ENTIRE reply is 3-5 lines, "
    "each starting with '- ' and at most 8 words: keywords, tools, numbers, employer. The first line is the direct "
    "answer. Nothing before the first line or after the last: no sentence, no paragraph, no intro, no closing. "
    "Coding tasks: the code first, then 2-3 cue lines. This overrides every other length or style instruction, "
    "and the style of earlier answers."
)

_cached_system_prompt = None
_cached_prompt_key = None

def _context_block(ctx: Dict[str, Any]) -> str:
    """The brief replaces the full resume when the session has one: about a third of the tokens,
    and only the experience that matters for this job. Without it the whole resume goes."""
    block = ""
    if ctx['talking_points'].strip():
        block += f"\n\n--- CANDIDATE BRIEF (YOUR experience, tailored to this job, plus how to answer) ---\n{ctx['talking_points'].strip()}"
    elif ctx['resume_text'].strip():
        block += f"\n\n--- CANDIDATE RESUME (YOUR experience) ---\n{ctx['resume_text'].strip()}"
    if ctx['job_description'].strip():
        block += f"\n\n--- JOB DESCRIPTION ---\n{ctx['job_description'].strip()}"
    return block

def get_system_prompt(ctx: Dict[str, Any]) -> str:
    """The session prompt: persona, rules, modes, brief or resume, JD. It is identical for every
    answer in a session, so it is built once and OpenAI's prompt cache bills it at the cached
    rate after the first answer."""
    global _cached_system_prompt, _cached_prompt_key
    import hashlib
    key = hashlib.sha256(json.dumps(ctx, sort_keys=True).encode('utf-8')).hexdigest()
    if _cached_system_prompt is not None and key == _cached_prompt_key:
        return _cached_system_prompt
    role = ctx['target_role'].strip() or 'the advertised'
    language = ctx['target_language'].strip() or 'Python'
    cue = bool(ctx['short_responses'])
    parts = [
        f"You are the candidate in a live job interview for a {role} position. Answer as yourself, in first person, "
        "as a real professional. Never say or hint that you are an AI.",
        "YOUR experience is the candidate brief or resume below. " + TRUTHFULNESS_RULES,
        "Use simple words and short sentences. Be confident but humble. Ground every answer in specifics from YOUR "
        "experience: tools, data, numbers.",
        "" if cue else "Keep spoken answers to 4-5 sentences unless the question clearly needs more.",
        f"Coding tasks: complete, working code in a fenced block tagged with its language (default {language}), then "
        "the approach and time/space complexity in 3-5 short sentences.",
        ESL_RULES if ctx['is_esl'] else "",
        CUE_RULES if cue else "",
    ]
    prompt = "\n\n".join(part for part in parts if part) + _context_block(ctx)
    _cached_system_prompt, _cached_prompt_key = prompt, key
    print(f"[CONTEXT] Session prompt built: ~{len(prompt) // 4} tokens")
    return prompt

def invalidate_context_cache():
    global _cached_system_prompt, _cached_prompt_key
    _cached_system_prompt = None
    _cached_prompt_key = None

def final_answer_rules(ctx: Dict[str, Any], screenshot: bool = False) -> dict:
    """Last system message before the question. The model follows what it read last, so the rules
    that got ignored at the top of a long prompt are repeated here."""
    rules = ["Before you answer: name a tool, platform or architecture at an employer only if YOUR brief or resume "
             "lists it under that employer. If the question assumes otherwise (e.g. 'with ADF at your current job'), "
             "correct it in a few words and say where you did use it. Use a number (%, volume, count, time saved) "
             "only if it appears in YOUR brief or resume."]
    if screenshot:
        rules.append("A screenshot of the candidate's screen is attached: answer or solve exactly what it shows. "
                     "For a coding problem, give complete working code.")
    if ctx.get('is_esl'):
        rules.append(ESL_RULES)
    if ctx.get('short_responses'):
        rules.append(CUE_RULES)
    return {"role": "system", "content": "\n\n".join(rules)}


# Auto-reset disabled - resume will persist between restarts

@app.get('/profile')
async def get_profile():
    # Never return secrets over HTTP - the UI doesn't need them back
    return {k: v for k, v in (profile_cache or {}).items() if k not in ('openai_api_key', 'license_key')}

@app.post('/validate-api-key')
async def validate_api_key(data: Dict[str, str]):
    """Validate OpenAI API key before allowing session creation"""
    global profile_cache
    api_key = data.get('api_key', '').strip()
    
    if not api_key:
        return {"valid": False, "error": "API key is required"}
    
    if not api_key.startswith('sk-'):
        return {"valid": False, "error": "Invalid API key format"}
    
    try:
        from openai import AsyncOpenAI
        await AsyncOpenAI(api_key=api_key).models.list()
        # Store key immediately on successful validation
        if not isinstance(profile_cache, dict):
            profile_cache = {}
        profile_cache['openai_api_key'] = api_key
        save_profile(profile_cache)
        print(f"[validate-api-key] Key validated and persisted to disk.")
        return {"valid": True}
    except Exception as e:
        error_msg = str(e)
        if "invalid_api_key" in error_msg or "Incorrect API key" in error_msg:
            return {"valid": False, "error": "Invalid API key"}
        elif "insufficient_quota" in error_msg:
            return {"valid": False, "error": "API key has no credits/quota"}
        else:
            return {"valid": False, "error": f"API key validation failed: {error_msg[:100]}"}

# License validation - Hardware-Locked
import hashlib
import platform
import subprocess


try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
except ImportError:
    print("WARNING: cryptography module not found. License validation will fail.")

# =============================================================================
# HARDWARE ID GENERATION
# =============================================================================
_hwid_cache = None  # Computed once, reused everywhere

def get_hwid():
    """Generate a unique Hardware ID. Identical algorithm to original — cached so
    it only runs once per process instead of twice (startup + license check)."""
    global _hwid_cache
    if _hwid_cache:
        return _hwid_cache
    try:
        # 1. CPU Serial/Info (same as original)
        cpu_info = ""
        try:
            # py-cpuinfo's CPUID probe runs in a multiprocessing child with a
            # busy-wait join; in the frozen exe that re-launches the whole backend.
            # On Windows brand_raw comes from the registry before CPUID is tried,
            # so skipping CPUID leaves the HWID unchanged (and takes ~80ms not ~3s).
            from cpuinfo import cpuinfo as _ci
            _ci.DataSource.can_cpuid = False
            info = _ci._get_cpu_info_internal()
            cpu_info = f"{info.get('brand_raw', '')}_{info.get('arch', '')}"
        except (ImportError, Exception):
            cpu_info = platform.processor()

        # 2. Machine Node/UUID (Mac Address based)
        import uuid
        mac_addr = hex(uuid.getnode())

        # 3. OS Info
        os_info = f"{platform.system()}_{platform.release()}"

        # Same hash formula as original — must not change
        raw_id = f"{cpu_info}_{mac_addr}_{os_info}"
        hwid = hashlib.sha256(raw_id.encode()).hexdigest().upper()
        _hwid_cache = f"{hwid[:4]}-{hwid[4:8]}-{hwid[8:12]}-{hwid[12:16]}"
        return _hwid_cache
    except Exception as e:
        print(f"HWID Error: {e}")
        return "UNKNOWN-HWID-0000"

# =============================================================================
# LICENSE VERIFICATION (RSA)
# =============================================================================
# =============================================================================
# LICENSE VERIFICATION (RSA)
# =============================================================================
# (PUBLIC_KEY_FILE and PRIVATE_KEY_FILE moved to top of file after BASE_DIR)

def ensure_keys_exist():
    """Ensure bundled public key exists. Auto-generation disabled in production."""
    if os.path.exists(PUBLIC_KEY_FILE):
        return

    print("[WARNING] Public key missing. Application will run in demo mode.")

# Call on import/startup
def initialize_keys():
    """Ensure keys exist and enforce bundled public key usage."""
    # 1. If running as frozen executable, overwrite public key from bundle
    if getattr(sys, 'frozen', False):
        try:
            # PyInstaller extracts to sys._MEIPASS
            bundle_dir = sys._MEIPASS
            bundled_key_path = os.path.join(bundle_dir, PUBLIC_KEY_NAME)
            
            if os.path.exists(bundled_key_path):
                # Copy bundled key to BASE_DIR (overwrite existing)
                dest_path = PUBLIC_KEY_FILE
                import shutil
                shutil.copy2(bundled_key_path, dest_path)
                print(f"[STARTUP] Enforced bundled public key: {dest_path}")
        except Exception as e:
            print(f"[STARTUP ERROR] Failed to copy bundled key: {e}")

    # 2. Generate keys if still missing (e.g. dev mode or missing bundle)
    ensure_keys_exist()

def check_saved_license():
    """Restore license state from profile on backend startup."""
    global is_licensed_backend
    try:
        profile = load_profile()
        saved_key = profile.get('license_key')
        if saved_key:
            current_hwid = get_hwid()
            if verify_license_signature(current_hwid, saved_key):
                is_licensed_backend = True
                print(f"[STARTUP] License restored from profile — full session mode active")
            else:
                print(f"[STARTUP] Saved license invalid for current HWID — demo mode")
        else:
            print(f"[STARTUP] No saved license — demo mode")
    except Exception as e:
        print(f"[STARTUP ERROR] License check failed: {e}")

# Both MUST run synchronously and in this order — called after all
# function definitions below to avoid NameError in PyInstaller exe.

import hashlib
def load_public_key():
    """Load public key from file (Prioritize Bundled)."""
    # 1. Try bundled key first (if frozen)
    if getattr(sys, 'frozen', False):
        try:
            bundle_dir = sys._MEIPASS
            bundled_path = os.path.join(bundle_dir, PUBLIC_KEY_NAME)
            if os.path.exists(bundled_path):
                print(f"[VERIFY] Using bundled key from: {bundled_path}")
                with open(bundled_path, "rb") as f:
                    return f.read()
        except Exception as e:
            print(f"[VERIFY ERROR] Bundled key read failed: {e}")

    # 2. Fallback to local file (Dev mode or missing bundle)
    if os.path.exists(PUBLIC_KEY_FILE):
        print(f"[VERIFY] Using local key from: {PUBLIC_KEY_FILE}")
        with open(PUBLIC_KEY_FILE, "rb") as f:
            return f.read()
    return None

def verify_license_signature(hwid: str, license_key_b64: str) -> bool:
    """Verify that the license key is a valid signature of the HWID."""
    try:
        pub_key_bytes = load_public_key()
        if not pub_key_bytes:
            print("ERROR: Public key not found for verification.")
            return False
            
        public_key = serialization.load_pem_public_key(pub_key_bytes)

        # 0. Sanitize Input (Remove all whitespace/newlines)
        license_key_b64 = "".join(license_key_b64.split())

        # 1. Strict Format Check (Regex)
        import re
        import base64
        # RSA-2048 signature in B64 is exactly 344 chars (including ==)
        if not re.match(r'^[A-Za-z0-9+/]{342}==$', license_key_b64):
            print("ERROR: Invalid license key format or length.")
            return False

        # 2. Decode License Key (Base64 -> Bytes)
        try:
            signature = base64.b64decode(license_key_b64, validate=True)
        except Exception:
            print("ERROR: Base64 decoding failed.")
            return False

        # 3. Strict Length Check
        if len(signature) != 256:  # RSA-2048 specific (2048/8)
            print(f"ERROR: Invalid signature length ({len(signature)} bytes).")
            return False

        # 4. Verify Signature
        public_key.verify(
            signature,
            hwid.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except (InvalidSignature, Exception) as e:
        print(f"License Verification Failed: {e}")
        return False

@app.get('/get-hwid')
async def endpoint_get_hwid():
    """Return the Machine's HWID for the user to copy."""
    return {"hwid": get_hwid()}

@app.post('/validate-license')
async def validate_license(data: Dict[str, str]):
    """Validate license key against HWID using RSA signature."""
    license_key = data.get('license_key', '').strip()
    
    if not license_key:
        return {"valid": False, "status": "empty"}
    
    current_hwid = get_hwid()
    
    if verify_license_signature(current_hwid, license_key):
        global is_licensed_backend, profile_cache
        is_licensed_backend = True
        if not isinstance(profile_cache, dict):
            profile_cache = {}
        profile_cache['license_key'] = license_key
        save_profile(profile_cache)
        print(f"[LICENSE] Valid license persisted for HWID: {current_hwid}")
        return {"valid": True, "status": "valid"}
    
    return {"valid": False, "status": "invalid"}

# Demo state lives in the profile (demo_started_at / last_demo_end_time, epoch ms)
# so restarting the backend no longer resets the 12-minute limit or the cooldown.
import time
import math

def _now_ms() -> float:
    return time.time() * 1000

def _profile() -> Dict[str, Any]:
    global profile_cache
    if not isinstance(profile_cache, dict):
        profile_cache = {}
    return profile_cache

def demo_cooldown_remaining_ms() -> float:
    p = _profile()
    started = p.get('demo_started_at')
    if started:
        if _now_ms() - started < DEMO_LIMIT_MS:
            return 0  # a demo is still running
        last_end = started + DEMO_LIMIT_MS  # ran out without a clean end
    else:
        last_end = p.get('last_demo_end_time') or 0
    return max(0, last_end + DEMO_COOLDOWN_MS - _now_ms())

def start_demo() -> Optional[str]:
    """Start (or resume) a demo window. Returns an error message if in cooldown."""
    _license_checked.wait(10)
    if is_licensed_backend:
        return None
    p = _profile()
    started = p.get('demo_started_at')
    if started and _now_ms() - started < DEMO_LIMIT_MS:
        return None  # resume the running demo; the clock does not restart
    remaining = demo_cooldown_remaining_ms()
    if remaining > 0:
        return f"Demo cooldown active. Try again in {math.ceil(remaining / 60000)} min."
    p['demo_started_at'] = _now_ms()
    p.pop('last_demo_end_time', None)
    save_profile(p)
    print(f"[SECURITY] Demo session started at {p['demo_started_at']}")
    return None

def end_demo():
    p = _profile()
    started = p.pop('demo_started_at', None)
    if started:
        p['last_demo_end_time'] = min(_now_ms(), started + DEMO_LIMIT_MS)
        save_profile(p)
        print("[SECURITY] Demo session ended. Cooldown started.")

def check_access_allowed() -> bool:
    """Enforce hardware-locked licensing and trial limits."""
    _license_checked.wait(10)
    if is_licensed_backend:
        return True
    started = _profile().get('demo_started_at')
    if not started:
        return False  # no demo running - one must be started via /session/save or /session/load
    return _now_ms() - started <= DEMO_LIMIT_MS



# ============ SESSION MANAGEMENT ============
# Sessions are stored in: BASE_DIR/sessions/<session_name>/
# Each session folder contains:
#   - session.json (metadata, job description, resume text)
#   - resume.docx (original resume file)
#   - conversation.json (all Q&A pairs)

SESSIONS_DIR = BASE_DIR / 'sessions'
current_session_name = None

from fastapi import HTTPException

_BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def safe_session_dir(session_name: str) -> Path:
    """Map a client-supplied session name to its folder, refusing anything that
    could escape SESSIONS_DIR ('..', separators, drive letters, absolute paths).
    Without this, DELETE /session/delete/..%2F.. would rmtree outside the app."""
    name = (session_name or '').strip()
    if not name or name in ('.', '..') or _BAD_NAME_CHARS.search(name):
        raise HTTPException(status_code=400, detail="Invalid session name")
    root = SESSIONS_DIR.resolve()
    target = (root / name).resolve()
    if target.parent != root:
        raise HTTPException(status_code=400, detail="Invalid session name")
    return target

def safe_upload_name(filename: str) -> str:
    """Keep only the base name of an uploaded file, minus path tricks."""
    name = Path((filename or '').replace(chr(92), '/')).name  # chr(92) = backslash
    name = _BAD_NAME_CHARS.sub('_', name).strip(' .')
    if not name or not name.lower().endswith('.docx'):
        raise HTTPException(status_code=400, detail="Only .docx files supported")
    return name

def save_conversation_to_session(question: str, response: str, had_screenshot: bool = False, model: str = "", response_time: float = 0, total_time: float = 0, cost: float = 0, input_tokens: int = 0, output_tokens: int = 0):
    """Helper function to save a Q&A pair to the current session"""
    
    if not current_session_name:
        return
    
    session_dir = safe_session_dir(current_session_name)
    conv_file = session_dir / 'conversation.json'
    
    try:
        if conv_file.exists():
            conversation = json.loads(conv_file.read_text(encoding='utf-8'))
        else:
            conversation = []
        
        from datetime import datetime
        entry = {
            'timestamp': datetime.now().isoformat(),
            'question': question,
            'response': response,
            'had_screenshot': had_screenshot,
            'model': model,
            'response_time': round(response_time, 1),
            'total_time': round(total_time, 1),
            'cost': round(cost, 6),
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }
        conversation.append(entry)
        
        conv_file.write_text(json.dumps(conversation, indent=2), encoding='utf-8')
        print(f"[SESSION] Auto-saved conversation entry #{len(conversation)}")
    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")

@app.post('/session/create')
async def create_session(data: Dict[str, str]):
    """Create a new session folder (it becomes active in /session/save)"""
    
    session_name = data.get('session_name', '').strip()
    if not session_name:
        return {"status": "error", "error": "Session name is required"}
    
    session_dir = safe_session_dir(session_name)
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        print(f"[SESSION] Created session folder: {session_dir}")
        return {"status": "ok", "session_path": str(session_dir)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post('/session/resume')
async def upload_session_resume(file: UploadFile = File(...), session_name: str = Form(...)):
    """Store the resume in the session folder and return its text (used by /session/save)"""
    try:
        filename = safe_upload_name(file.filename)
        session_dir = safe_session_dir(session_name)
        session_dir.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        (session_dir / filename).write_bytes(content)
        text = _docx_text(content)
        print(f"[SESSION] Resume saved to {session_dir / filename} ({len(text)} chars of text)")
        return {"status": "ok", "resume_text": text, "resume_path": str(session_dir / filename)}
    except Exception as e:
        print(f"[SESSION RESUME ERROR] {e}")
        return {"status": "error", "error": str(e)}


BRIEF_INSTRUCTIONS = (
    "You prepare a job candidate for an interview. From their resume and the job description, write a brief "
    "that an interview assistant will use instead of the full resume. Plain text, no markdown headings or bold.\n\n"
    "RELEVANT EXPERIENCE\n"
    "For each employer that matters for this job: one line with role, company, dates, domain; then short bullets "
    "with the specifics that match the job description: tools, platforms, data types, volumes, numbers, and "
    "what the candidate personally owned. Keep every number and named technology that is relevant. Drop "
    "anything unrelated to this job.\n\n"
    "TALKING POINTS\n"
    "5-10 short bullets: which experience to lead with for this job's main requirements, the exact terms to use, "
    "and for each requirement the resume does not cover, how to answer honestly from adjacent experience.\n\n"
    "Each bullet must be concrete: what was built, with which tools, for which data, at what scale or result. "
    "Generic bullets like 'collaborated with stakeholders' are useless to the assistant; leave them out. "
    "Use only facts from the resume. Never invent employers, tools, numbers or projects. "
    "Attribute each tool and platform only to the employer whose resume section names it: if ADF appears under one job "
    "and not another, never list ADF under the other. Keep personal and certification projects labeled as such. "
    "Aim for 4000-6000 characters; never exceed 6000."
)


@app.post('/session/brief')
async def generate_session_brief(file: UploadFile = File(...), job_description: str = Form(...),
                                 target_role: str = Form(''), api_key: str = Form('')):
    """Draft the talking points for the setup screen: the resume condensed to what this JD needs, plus how to answer"""
    try:
        resume_text = _docx_text(await file.read())
        if not resume_text.strip():
            return {"status": "error", "error": "No text found in the resume"}
        if not job_description.strip():
            return {"status": "error", "error": "Paste the job description first"}

        # Once per session, and every answer builds on it: gpt-4o-mini kept moving tools
        # between employers here, so the stronger model is worth a few cents
        model = "gpt-4o"
        completion = await get_async_client(api_key.strip() or None).chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": BRIEF_INSTRUCTIONS},
                {"role": "user", "content": (
                    f"TARGET ROLE: {target_role.strip() or 'see job description'}\n\n"
                    f"--- JOB DESCRIPTION ---\n{job_description.strip()}\n\n"
                    f"--- RESUME ---\n{resume_text.strip()}"
                )},
            ],
            max_tokens=3000,
            temperature=0.2,
        )
        brief = (completion.choices[0].message.content or "").strip()
        track_completion_usage(completion.usage, model)
        print(f"[BRIEF] Generated {len(brief)} chars from a {len(resume_text)}-char resume")
        return {"status": "ok", "talking_points": brief}
    except Exception as e:
        print(f"[BRIEF ERROR] {e}")
        return {"status": "error", "error": str(e)}


@app.post('/session/save')
async def save_session_data(data: Dict[str, Any]):
    """Save a new session's settings and make it the active session"""
    
    session_name = data.get('session_name', '').strip()
    if not session_name:
        return {"status": "error", "error": "Session name is required"}
    
    session_dir = safe_session_dir(session_name)
    session_dir.mkdir(parents=True, exist_ok=True)
    
    demo_error = start_demo()
    if demo_error:
        return {"status": "error", "error": demo_error}

    session_file = session_dir / 'session.json'
    
    try:
        # Save session data
        session_data = {
            'session_name': session_name,
            'job_description': data.get('job_description', ''),
            'resume_text': data.get('resume_text', ''),
            'target_role': data.get('target_role', ''),
            'target_language': data.get('target_language', ''),
            'is_esl': data.get('is_esl', False),
            'short_responses': data.get('short_responses', False),
            'smart_interview': data.get('smart_interview', False),
            'talking_points': data.get('talking_points', ''),
            'created_at': data.get('created_at', ''),
            'updated_at': datetime.now().isoformat(),
            'text_model': data.get('text_model', DEFAULT_TEXT_MODEL),
            # API key is NOT stored per session - the global (encrypted) profile key is used
        }
        
        session_file.write_text(json.dumps(session_data, indent=2), encoding='utf-8')
        print(f"[SESSION] Saved session data to: {session_file}")
        
        # Initialize empty conversation file
        conv_file = session_dir / 'conversation.json'
        if not conv_file.exists():
            conv_file.write_text('[]', encoding='utf-8')
        
        # A newly typed key is remembered (encrypted) in the profile; the session itself never stores it
        new_key = data.get('openai_api_key', '').strip()
        if new_key.startswith("sk-") and not new_key.endswith("KiwA") and _profile().get('openai_api_key') != new_key:
            _profile()['openai_api_key'] = new_key
            save_profile(_profile())

        set_active_context(session_name, session_data)

        return {"status": "ok", "session_path": str(session_dir)}
    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")
        return {"status": "error", "error": str(e)}


@app.post('/session/conversation')
async def save_conversation_entry(data: Dict[str, Any]):
    """Save a conversation entry (question + response) to the session"""
    
    session_name = data.get('session_name') or current_session_name
    if not session_name:
        return {"status": "error", "error": "No active session"}
    
    session_dir = safe_session_dir(session_name)
    conv_file = session_dir / 'conversation.json'
    
    try:
        # Load existing conversation
        if conv_file.exists():
            conversation = json.loads(conv_file.read_text(encoding='utf-8'))
        else:
            conversation = []
        
        # Add new entry
        entry = {
            'timestamp': data.get('timestamp', ''),
            'question': data.get('question', ''),
            'response': data.get('response', ''),
            'had_screenshot': data.get('had_screenshot', False)
        }
        conversation.append(entry)
        
        # Save back
        conv_file.write_text(json.dumps(conversation, indent=2), encoding='utf-8')
        print(f"[SESSION] Saved conversation entry #{len(conversation)} to: {conv_file}")
        
        return {"status": "ok", "entry_count": len(conversation)}
    except Exception as e:
        print(f"[SESSION CONVERSATION ERROR] {e}")
        return {"status": "error", "error": str(e)}


@app.post('/session/said')
async def save_said(data: Dict[str, Any]):
    """Answer Review: attach what the candidate actually said to the last saved answer"""
    session_name = data.get('session_name') or current_session_name
    said = (data.get('said') or '').strip()
    if not session_name or not said:
        return {"status": "ok"}
    conv_file = safe_session_dir(session_name) / 'conversation.json'
    try:
        conversation = json.loads(conv_file.read_text(encoding='utf-8')) if conv_file.exists() else []
        if not conversation:
            return {"status": "ok"}
        last = conversation[-1]
        last['said'] = (last.get('said', '') + ' ' + said).strip()
        conv_file.write_text(json.dumps(conversation, indent=2), encoding='utf-8')
        return {"status": "ok"}
    except Exception as e:
        print(f"[SESSION SAID ERROR] {e}")
        return {"status": "error", "error": str(e)}


CRITIQUE_INSTRUCTIONS = (
    "You are an interview coach reviewing a mock or real interview. For each question you get what the "
    "interviewer asked, the answer an assistant suggested, and what the candidate actually said (speech-to-text, "
    "may have small errors). The suggestions were written by an assistant and are often wrong about which job "
    "used which tool. The RESUME is the only source of truth: a tool or architecture counts for a job only if "
    "that job's own section of the resume names it (the skills list does not count).\n\n"
    "Write plain text, no markdown headings or bold. For each question:\n"
    "Q<n>: <the question in a few words>\n"
    "- Suggestion check: each claim in the suggestion that the resume does not support for that job, "
    "e.g. 'ADF at AmeriBen - not in the AmeriBen section'. Write 'ok' if there are none.\n"
    "- Verdict: Strong / OK / Weak, with a one-line reason.\n"
    "- Covered: the key points the candidate actually made.\n"
    "- Missed: points the candidate left out that the resume supports and the interviewer wanted. "
    "Never list anything from the Suggestion check.\n"
    "- Say next time: the exact one or two sentences to say, in first person, using only resume facts for that "
    "same job (tools, data, numbers). Not advice like 'I will elaborate'.\n"
    "If nothing was captured for a question, write only 'Q<n>: <question> - not captured' on one line. "
    "End with OVERALL: the 3 most important things to practise before the next interview."
)


@app.post('/session/critique/{session_name}')
async def critique_session(session_name: str):
    """Answer Review: compare what was suggested with what the candidate said, per question.
    Runs only when the user clicks Critique; the result is saved as review.txt in the session."""
    session_dir = safe_session_dir(session_name)
    try:
        session_file = session_dir / 'session.json'
        conv_file = session_dir / 'conversation.json'
        data = json.loads(session_file.read_text(encoding='utf-8')) if session_file.exists() else {}
        conversation = json.loads(conv_file.read_text(encoding='utf-8')) if conv_file.exists() else []
        if not any(e.get('said') for e in conversation):
            return {"status": "error", "error": "No recorded answers in this session. Your answers are saved in Smart mode from this version on."}

        parts = []
        for n, e in enumerate((e for e in conversation if e.get('question')), 1):
            parts.append(f"Q{n} INTERVIEWER: {e['question'][:1500]}\n"
                         f"SUGGESTED: {(e.get('response') or '')[:2000]}\n"
                         f"CANDIDATE SAID: {e.get('said') or '(not captured)'}")
        # The resume, not the generated brief: the brief can carry the same mistakes as the suggestions
        background = (data.get('resume_text') or data.get('talking_points') or '').strip()[:30000]
        user = (f"ROLE: {data.get('target_role', '')}\n\n--- CANDIDATE RESUME ---\n{background}\n\n"
                f"--- INTERVIEW ---\n" + "\n\n".join(parts))[-60000:]
        user += "\n\nReminder: check every suggestion against the job's own resume section before judging."

        # One call per click, so the stronger model is worth it (a few cents)
        model = "gpt-4o"
        completion = await get_async_client().chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": CRITIQUE_INSTRUCTIONS}, {"role": "user", "content": user}],
            max_tokens=4000,
            temperature=0.3,
        )
        review = (completion.choices[0].message.content or "").strip()
        track_completion_usage(completion.usage, model)
        (session_dir / 'review.txt').write_text(review, encoding='utf-8')
        print(f"[REVIEW] Critique for '{session_name}': {len(review)} chars")
        return {"status": "ok", "review": review}
    except Exception as e:
        print(f"[REVIEW ERROR] {e}")
        return {"status": "error", "error": str(e)}


@app.post('/session/end')
async def end_session(data: Dict[str, str]):
    """Finalize and close a session"""

    session_name = data.get('session_name') or current_session_name
    if not session_name:
        return {"status": "ok", "message": "No session to end"}

    try:
        # Q&A pairs are already written to conversation.json as each answer
        # completes, so there is nothing left to append here.
        if not is_licensed_backend:
            end_demo()

        clear_active_context()
        print(f"[SESSION] Ended session: {session_name} (context and conversation memory cleared)")
        return {"status": "ok", "message": f"Session '{session_name}' ended"}

    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get('/sessions')
async def list_sessions():
    """List all available sessions"""
    try:
        if not SESSIONS_DIR.exists():
            return {"sessions": []}
        
        sessions = []
        for session_dir in SESSIONS_DIR.iterdir():
            if session_dir.is_dir():
                session_file = session_dir / 'session.json'
                if session_file.exists():
                    data = json.loads(session_file.read_text(encoding='utf-8'))
                    sessions.append({
                        'name': session_dir.name,
                        'created_at': data.get('created_at', ''),
                        'target_role': data.get('target_role', ''),
                        'target_language': data.get('target_language', ''),
                        'job_description_preview': data.get('job_description', '')[:100]
                    })
        
        # Sort sessions by created_at descending (newest first)
        sessions.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return {"sessions": sessions}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@app.get('/session/load/{session_name}')
async def load_session(session_name: str):
    """Read a saved session for the Past Sessions view. Read-only: viewing a session does not
    activate it (that is /session/activate, on Resume)."""
    try:
        session_dir = safe_session_dir(session_name)
        session_file = session_dir / 'session.json'
        if not session_file.exists():
            return {"status": "error", "error": "Session not found"}

        data = json.loads(session_file.read_text(encoding='utf-8'))
        if data.pop('openai_api_key', None):
            # Older versions saved the key in plain text per session - remove it
            session_file.write_text(json.dumps(data, indent=2), encoding='utf-8')

        conv_file = session_dir / 'conversation.json'
        try:
            history = json.loads(conv_file.read_text(encoding='utf-8')) if conv_file.exists() else []
        except Exception:
            history = []
        review_file = session_dir / 'review.txt'

        return {
            "status": "ok",
            "session_name": session_name,
            "resume_text": data.get('resume_text', ''),
            "job_description": data.get('job_description', ''),
            "talking_points": data.get('talking_points', ''),
            "target_role": data.get('target_role', ''),
            "target_language": data.get('target_language', ''),
            "is_esl": bool(data.get('is_esl', False)),
            "short_responses": bool(data.get('short_responses', False)),
            "smart_interview": bool(data.get('smart_interview', False)),
            "created_at": data.get('created_at', ''),
            "text_model": data.get('text_model', DEFAULT_TEXT_MODEL),
            "review": review_file.read_text(encoding='utf-8') if review_file.exists() else '',
            "history": history
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post('/session/activate')
async def activate_session(data: Dict[str, str]):
    """Resume a saved session: its resume/brief/JD/modes become the answer context, with a fresh
    conversation memory (earlier answers stay in the session file, not in the prompt)"""
    global session_usage
    try:
        session_name = (data.get('session_name') or '').strip()
        session_file = safe_session_dir(session_name) / 'session.json'
        if not session_file.exists():
            return {"status": "error", "error": "Session not found"}
        demo_error = start_demo()
        if demo_error:
            return {"status": "error", "error": demo_error}
        set_active_context(session_name, json.loads(session_file.read_text(encoding='utf-8')))
        session_usage = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0, "request_count": 0,
                         "ai_cost": 0.0, "transcription_seconds": 0.0, "transcription_cost": 0.0}
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete('/session/delete/{session_name}')
async def delete_session(session_name: str):
    """Delete a session and all its contents"""
    try:
        import shutil
        session_dir = safe_session_dir(session_name)
        
        if not session_dir.exists():
            return {"status": "error", "error": "Session not found"}
        
        shutil.rmtree(session_dir)
        print(f"[SESSION] Deleted session: {session_name}")
        
        return {"status": "ok", "message": f"Session '{session_name}' deleted"}
    except Exception as e:
        print(f"[SESSION DELETE ERROR] {e}")
        return {"status": "error", "error": str(e)}

# ============ END SESSION MANAGEMENT ============


@app.post('/conversation/clear')
async def clear_conversation():
    """Clear conversation history to start a fresh session"""
    reset_conversation_context()
    print("[CONVERSATION] Conversation memory cleared")
    return {"status": "ok", "message": "Conversation history cleared"}


@app.get('/conversation/history')
async def get_conversation_history():
    """Get current conversation history (for debugging)"""
    return {"history": conversation_history, "notes": conversation_notes, "count": len(conversation_history)}


@app.get('/usage')
async def get_usage():
    """Get current session API usage and cost"""
    return session_usage


@app.post('/usage/reset')
async def reset_usage():
    """Reset usage counters"""
    global session_usage
    session_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_cost": 0.0,
        "request_count": 0,
        "ai_cost": 0.0,
        "transcription_seconds": 0.0,
        "transcription_cost": 0.0
    }
    return {"status": "ok", "message": "Usage reset"}

# ----------------------------------------------------------------------------

# ============ SMART INTERVIEW ============
SMART_INTERVIEW_INSTRUCTIONS = (
    "SMART INTERVIEW MODE: the user message is a live exchange transcribed from a call, labeled by speaker: "
    "'Interviewer:' lines are the interviewer, 'Me:' lines are you, the candidate. Answer the interviewer's latest "
    "question or task. If you asked a clarifying question and the interviewer answered it, follow that clarification "
    "exactly; never answer your own clarifying questions. If the interviewer is clarifying or changing a question "
    "answered earlier, give the revised answer. A 'Me (just said):' line is the end of what you said right before; "
    "use it only as context. Transcripts contain speech-to-text errors; infer the intended words. "
    "Never start your reply with a speaker label."
)


class SmartClassifyRequest(BaseModel):
    exchange: str = ""
    previous_question: str = ""

    model_config = {"extra": "ignore"}


@app.post("/smart/classify")
async def smart_classify(req: SmartClassifyRequest):
    """Fast yes/no: should the candidate answer now? Used only for interviewer turns
    the client-side question heuristics can't decide."""
    if not check_access_allowed() or not req.exchange.strip():
        return {"answer_now": False}
    prompt = (
        "You watch a live job interview transcript. Decide whether the interviewer has just "
        "finished a question, task, or clarification that the candidate should respond to now. "
        "Answer NO for small talk, acknowledgements, an unfinished sentence, or the interviewer "
        "still explaining before asking. Question marks come from speech-to-text and are often wrong: "
        "judge from the words, not the punctuation. Reply with exactly YES or NO."
    )
    user = req.exchange.strip()[-2000:]
    if req.previous_question.strip():
        user = f"(Previously answered question: {req.previous_question.strip()[-500:]})\n\n{user}"
    try:
        client = get_async_client()
        res = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}],
            max_tokens=1,
            temperature=0,
        )
        track_completion_usage(res.usage, "gpt-4o-mini")
        verdict = (res.choices[0].message.content or "").strip().upper()
        print(f"[SMART] classify -> {verdict}")
        return {"answer_now": verdict.startswith("Y")}
    except Exception as e:
        print(f"[SMART] classify error: {e}")
        return {"answer_now": False}


@app.post("/ai/stream")
async def stream_ai_response(req: AIRequest):
    """Stream one answer as Server-Sent Events.

    What the model gets, in this order (fixed parts first, so OpenAI's prompt cache covers them):
      1. the session prompt: persona, rules, modes, brief or resume, JD     (get_system_prompt)
      2. Smart Interview instructions, when the question comes from Smart mode
      3. one line per older question, at most MAX_NOTES                    (conversation_notes)
      4. the last HISTORY_TURNS questions and answers verbatim             (conversation_history)
      5. final rules: truthfulness, screenshot, ESL/Cue format - read last, so they win
      6. the question (Smart: the labeled exchange), plus the screenshot
    """
    async def generate_stream():
        if not check_access_allowed():
            yield f"data: {json.dumps({'error': 'Demo expired. Please purchase a license to continue.'})}\n\n"
            return
        ctx = get_active_context()
        if not ctx:
            yield f"data: {json.dumps({'error': 'No active session. Create or resume a session first.'})}\n\n"
            return

        import time as _time
        try:
            client = get_async_client()
            messages = [{"role": "system", "content": get_system_prompt(ctx)}]
            if req.smart_mode:
                messages.append({"role": "system", "content": SMART_INTERVIEW_INSTRUCTIONS})
            if conversation_notes:
                messages.append({"role": "system", "content": "Earlier in this interview (one line per question; "
                                 "stay consistent with what you said):\n" + "\n".join(conversation_notes)})
            messages.extend(conversation_history)
            messages.append(final_answer_rules(ctx, screenshot=bool(req.screenshot)))
            if req.screenshot:
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": req.transcript},
                    {"type": "image_url", "image_url": {"url": req.screenshot}},
                ]})
            else:
                messages.append({"role": "user", "content": req.transcript})

            # Screenshots use the selected model too: all of them read images, and coding
            # problems are where the stronger model matters most
            model = req.text_model if req.text_model in AVAILABLE_TEXT_MODELS else DEFAULT_TEXT_MODEL
            if model.startswith("gpt-5"):
                # Reasoning models: thinking tokens need headroom; temperature is unsupported
                token_param = {"max_completion_tokens": 16384}
            else:
                token_param = {"max_tokens": 2048, "temperature": 0.7}
            print(f"[STREAM] {model} | smart={req.smart_mode} screenshot={bool(req.screenshot)} | "
                  f"notes={len(conversation_notes)} history={len(conversation_history) // 2} turns")

            yield f"data: {json.dumps({'heartbeat': True})}\n\n"
            _start_time = _time.time()
            try:
                # prompt_cache_key routes every answer of this session to the same OpenAI cache,
                # so the fixed session prompt is billed at the cached rate after the first answer
                completion = await client.chat.completions.create(
                    model=model, messages=messages, stream=True,
                    stream_options={"include_usage": True},
                    prompt_cache_key=f"session-{_cached_prompt_key[:24]}", **token_param)
            except Exception as create_err:
                print(f"[STREAM] OpenAI create() error: {create_err}")
                err_text = str(create_err)
                if "insufficient_quota" in err_text:
                    err_text = "OUT_OF_CREDITS: Your OpenAI account is out of credits."
                yield f"data: {json.dumps({'error': err_text})}\n\n"
                return

            full_response = ""
            _ttft = 0
            usage = None
            try:
                async for chunk in completion:
                    if chunk.usage:
                        usage = chunk.usage  # last chunk: real token counts, incl. cached
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        if not full_response:
                            _ttft = _time.time() - _start_time
                        full_response += content
                        yield f"data: {json.dumps({'chunk': content})}\n\n"
            except Exception as iter_err:
                print(f"[STREAM] Iteration error: {iter_err}")
                yield f"data: {json.dumps({'error': str(iter_err)[:200]})}\n\n"
                return

            if not full_response.strip():
                print(f"[STREAM] WARNING: Model {model} returned empty response")
                yield f"data: {json.dumps({'error': f'Model {model} returned an empty response. The model may not support this request format.'})}\n\n"
                return

            # Cost from OpenAI's own counts; a local estimate only if they're missing
            if usage:
                details = getattr(usage, 'prompt_tokens_details', None)
                cached_tokens = (getattr(details, 'cached_tokens', 0) or 0) if details else 0
                input_tokens, output_tokens, image_tokens = usage.prompt_tokens, usage.completion_tokens, 0
            else:
                input_tokens = count_tokens("\n".join(m['content'] if isinstance(m['content'], str) else req.transcript for m in messages))
                output_tokens = count_tokens(full_response)
                image_tokens = estimate_image_tokens(req.screenshot, model) if req.screenshot else 0
                cached_tokens = 0
            response_cost = update_usage(input_tokens, output_tokens, model, image_tokens, cached_tokens)
            _total_time = _time.time() - _start_time

            # Memory gets the question as asked (Smart: the interviewer's question, without the
            # "Me (just said)" context that only mattered for this answer)
            question = (req.display_question or req.transcript).strip()
            if req.screenshot:
                question = f"[Screenshot] {question}"
            if req.save_to_context is not False:
                record_turn(question, full_response)
            if current_session_name:
                try:
                    save_conversation_to_session(question, full_response, bool(req.screenshot), model,
                                                 response_time=_ttft, total_time=_total_time, cost=response_cost,
                                                 input_tokens=input_tokens, output_tokens=output_tokens)
                except Exception as save_err:
                    print(f"[SESSION SAVE ERROR] {save_err}")

            yield f"data: {json.dumps({'done': True, 'model': model, 'usage': session_usage, 'response_in_tokens': input_tokens, 'response_cached_tokens': cached_tokens, 'response_out_tokens': output_tokens, 'response_cost': round(response_cost, 6), 'ttft': round(_ttft, 2), 'total_time': round(_total_time, 2)})}\n\n"

        except Exception as e:
            print(f"Streaming AI Error: {e}")
            yield f"data: {json.dumps({'error': str(e)[:200]})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


# ── Startup sequence ────────────────────────────────────────────────────────
# Must run AFTER all function definitions so PyInstaller exe doesn't hit
# NameError on verify_license_signature / load_public_key etc.
# Order matters:
#   1. initialize_keys  — copies/generates public key so verify can find it
#   2. check_saved_license — reads profile and verifies RSA signature
initialize_keys()

def _warm_up():
    """Runs in the background so /health answers as soon as FastAPI is up:
    restores the saved license (HWID takes ~1 s), then loads openai, tiktoken
    and the client so the first answer doesn't stall the server."""
    try:
        check_saved_license()
    finally:
        _license_checked.set()
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