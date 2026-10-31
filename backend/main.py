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

# GPT pricing (per 1M tokens) - Updated December 2025
PRICING = {
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-4o-mini": {"input": 0.60, "output": 2.40},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-5-nano": {"input": 0.15, "output": 0.60},
    "gpt-5-mini": {"input": 0.50, "output": 1.50}
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
DEFAULT_SCREENSHOT_MODEL = "gpt-4o-mini"

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

def calculate_cost(input_tokens: int, output_tokens: int, model: str = "gpt-4o", image_tokens: int = 0) -> float:
    """Calculate cost in dollars"""
    pricing = PRICING.get(model, PRICING["gpt-4o"])
    total_input = input_tokens + image_tokens
    input_cost = (total_input / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return (input_cost + output_cost) * 1.10  # 10% buffer

def update_usage(input_tokens: int, output_tokens: int, model: str = "gpt-3.5-turbo", image_tokens: int = 0):
    """Update session usage stats"""
    global session_usage
    session_usage["input_tokens"] += input_tokens + image_tokens
    session_usage["output_tokens"] += output_tokens
    cost = calculate_cost(input_tokens, output_tokens, model, image_tokens)
    session_usage["total_cost"] += cost
    session_usage["ai_cost"] = session_usage.get("ai_cost", 0.0) + cost
    session_usage["request_count"] += 1
    print(f"[USAGE] Total: ${session_usage['total_cost']:.4f} ({session_usage['request_count']} requests, {image_tokens} image tokens)")

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
    transcription = {"model": model}
    if role and model != FALLBACK_TRANSCRIBE_MODEL:
        # Biases spelling of technical terms toward the interview's domain
        transcription["prompt"] = f"Live job interview for a {role} role. Technical vocabulary is common."
    audio_input = {
        "format": {"type": "audio/pcm", "rate": 24000},
        "transcription": transcription,
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.45,
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

# Conversation history for session context
# Stores list of {"role": "user"/"assistant", "content": "..."} messages
conversation_history = []

# Rolling summary — compressed memory of turns that have been evicted from conversation_history.
# Built incrementally: each time a turn ages out, gpt-4o-mini summarizes it and appends to this string.
# Injected as a [CONTEXT NOTE] system message on every request so the AI always has full session memory.
conversation_summary = ""

# Bumped whenever the conversation is reset, so a background summary that
# finishes after the session ended can't leak into the next session.
_context_epoch = 0
_background_tasks = set()

def reset_conversation_context():
    global conversation_history, conversation_summary, _context_epoch
    conversation_history = []
    conversation_summary = ""
    _context_epoch += 1

async def _summarize_in_background(turns: list, api_key: str, epoch: int):
    global conversation_summary
    new_chunk = await summarize_old_turns(turns, api_key)
    if new_chunk and epoch == _context_epoch:
        conversation_summary = (conversation_summary + "\n" + new_chunk).strip() if conversation_summary else new_chunk

def evict_old_turns():
    """Rolling summary: keep the 3 most recent turns (6 msgs) verbatim; summarize
    anything older in the background so the client gets 'done' immediately."""
    global conversation_history
    if len(conversation_history) <= 6:
        return
    turns_to_evict = conversation_history[:-6]
    conversation_history = conversation_history[-6:]
    task = asyncio.create_task(_summarize_in_background(turns_to_evict, get_api_key(), _context_epoch))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

# ============ CACHED SYSTEM CONTEXT ============
# The system prompt containing the full resume + job description is VERY expensive
# (~5000 tokens) if rebuilt and resent on every single request.
# We build it ONCE when the session starts (or when the profile changes) and cache it.
# Subsequent questions only send the slim role-instruction system prompt + conversation tail.

_cached_system_context = None   # Full system prompt string (with resume & JD)
_cached_context_hash = None     # Hash of inputs that produced the cache — used to detect profile changes

def _build_context_hash(role: str, language: str, resume_text: str, job_description: str) -> str:
    import hashlib
    # Hash the full text, not just lengths: a new resume of the same length must rebuild the cache
    raw = "\x1f".join([role or '', language or '', resume_text or '', job_description or ''])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def _compress_context(resume_text: str, job_description: str, max_resume_chars: int = 2400, max_jd_chars: int = 1200) -> str:
    """Trim resume and JD to a token-efficient size while preserving the most important parts.
    
    Resume: keep the first ~2400 chars (covers summary, skills, most recent 1-2 roles).
    JD: keep the first ~1200 chars (covers title, requirements, key responsibilities).
    Combined this stays well under ~1000 tokens for context, vs 4000+ for a full document.
    """
    context_block = ""
    if resume_text and resume_text.strip():
        trimmed = resume_text.strip()
        if len(trimmed) > max_resume_chars:
            trimmed = trimmed[:max_resume_chars] + "\n[...resume truncated for brevity...]"
        context_block += f"\n\n--- CANDIDATE RESUME ---\n{trimmed}\n"
    if job_description and job_description.strip():
        trimmed_jd = job_description.strip()
        if len(trimmed_jd) > max_jd_chars:
            trimmed_jd = trimmed_jd[:max_jd_chars] + "\n[...JD truncated for brevity...]"
        context_block += f"\n\n--- JOB DESCRIPTION ---\n{trimmed_jd}\n"
    return context_block

def get_system_context(role: str, language: str, resume_text: str, job_description: str, for_vision: bool = False, is_esl: bool = False, short_responses: bool = False) -> str:
    """Return a cached system prompt. Only rebuilds when role/language/resume/JD/modifiers changes."""
    global _cached_system_context, _cached_context_hash

    # Include modifiers in hash to rebuild cache if they change
    new_hash = _build_context_hash(role, language, resume_text, job_description) + f"|{is_esl}|{short_responses}"

    if _cached_system_context is not None and _cached_context_hash == new_hash and not for_vision:
        print("[CONTEXT CACHE] Hit — reusing cached system context (0 extra resume tokens)")
        return _cached_system_context

    print(f"[CONTEXT CACHE] {'Miss' if _cached_system_context else 'Cold start'} — building system context")

    # Use compressed context to keep input tokens low (~800 tokens vs 4000+ raw)
    context_block = _compress_context(resume_text, job_description)

    # Add Modifiers - Make them extremely strict
    modifier_block = ""
    if is_esl:
        modifier_block += "\n\nCRITICAL CONSTRAINT: The user speaks English as a second language. Use short simple sentences. One idea per sentence. Avoid idioms and figures of speech (e.g. 'hit the ground running', 'boiling the ocean'). Keep technical terms but explain them briefly when first used. Never use compound or multi-clause sentences."
    if short_responses:
        modifier_block += "\n\nCRITICAL CONSTRAINT: Maximum 3 sentences or 5 bullet points total. No filler openers. Stop after answering the question. Do not elaborate."

    if for_vision:
        # Vision requests need the context inline — do NOT cache these
        return (
            f"CRITICAL: You ARE the job candidate in this interview for a {role} position. "
            "You are NOT an AI assistant. NEVER say 'I am an AI' or 'I don't have experience'. "
            "The resume below is YOUR real work history. When asked about past jobs, refer to YOUR resume. "
            "Speak in FIRST PERSON as yourself - a real human professional. "
            "When you see a coding problem, SOLVE IT with working code and clear explanation. "
            "Use simple words. Short sentences. One idea per sentence. "
            "Explain your approach in 6-8 sentences maximum. Write clean code with comments, then explain simply. "
            "Draw from YOUR resume for all experience-related questions. "
            f"Prefer {language or 'Python'} for all coding and technical explanations. "
            "Remember what was discussed earlier."
            f"{modifier_block}"
            f"{context_block}"
        )

    system_prompt = (
        f"CRITICAL: You ARE the job candidate in this interview for a {role} position. "
        "You are NOT an AI assistant. NEVER say 'I am an AI' or 'I don't have experience' or 'I cannot'. "
        "The resume below is YOUR real work history. You ARE this person with this background. "
        "When asked about previous jobs, projects, or experience - use details from YOUR resume. "
        "Speak in FIRST PERSON as yourself - a real human professional. "
        "Use simple words. Short sentences. One idea per sentence. "
        "Be confident but humble. Keep answers to 4-5 sentences. Give specific examples from YOUR resume. "
        "Remember what was discussed earlier in this conversation. "
        f"Prefer {language or 'Python'} for all coding and technical explanations. "
        "If you write ANY code, you MUST wrap it strictly inside standard Markdown content blocks specifying the exact language (e.g. ```python ... ```)."
        f"{modifier_block}"
        f"{context_block}"
    )

    _cached_system_context = system_prompt
    _cached_context_hash = new_hash
    tok_estimate = len(system_prompt) // 4
    print(f"[CONTEXT CACHE] Cached. System prompt ~{tok_estimate} tokens (compressed from raw docs).")
    return system_prompt

def invalidate_context_cache():
    """Call this when the profile/resume is updated so the cache is rebuilt on next request."""
    global _cached_system_context, _cached_context_hash
    _cached_system_context = None
    _cached_context_hash = None
    print("[CONTEXT CACHE] Invalidated. Will rebuild on next request.")


async def summarize_old_turns(turns_to_summarize: list, api_key: str) -> str:
    """Summarize a list of evicted conversation turns into a compact context note.
    Uses gpt-4o-mini (cheapest model) — typically costs ~$0.0001 per call.
    Returns a short paragraph describing what was discussed and any key decisions/code.
    """
    if not turns_to_summarize or not api_key:
        return ""
    
    # Format turns into readable Q&A text
    qa_text = ""
    for msg in turns_to_summarize:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        qa_text += f"{role_label}: {msg['content'][:800]}\n\n"  # Cap per-message length
    
    try:
        resp = await get_async_client(api_key).chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a compact note-taker. Summarize the following Q&A exchange in 2-3 sentences. "
                        "Focus on: what was asked/discussed, key technical decisions or code produced, and any "
                        "important context needed to answer follow-up questions. Be concise but technically precise."
                    )
                },
                {"role": "user", "content": qa_text}
            ],
            max_tokens=200,
            temperature=0.0
        )
        summary_text = resp.choices[0].message.content.strip()
        in_tok = resp.usage.prompt_tokens
        out_tok = resp.usage.completion_tokens
        summary_cost = calculate_cost(in_tok, out_tok, "gpt-4o-mini")
        print(f"[SUMMARY] Summarized {len(turns_to_summarize)} msgs → {len(summary_text)} chars | "
              f"{in_tok} in / {out_tok} out tokens | cost ${summary_cost:.6f}")
        return summary_text
    except Exception as e:
        print(f"[SUMMARY ERROR] Failed to summarize old turns: {e}")
        return ""  # Non-fatal — just lose the summary for this turn

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



@app.post('/profile')
async def post_profile(data: Dict[str, Any]):
    global profile_cache
    try:
        # Keys the client must not be able to overwrite or wipe
        protected = ('openai_api_key', 'license_key', 'demo_started_at', 'last_demo_end_time')
        merged = {k: v for k, v in data.items() if k not in protected}
        for k in protected:
            if k in _profile():
                merged[k] = _profile()[k]
        save_profile(merged)
        profile_cache = merged
        invalidate_context_cache()  # Role/JD may have changed, rebuild system context next time
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


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
    global current_session_name
    
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
    """Create a new session folder"""
    global current_session_name
    
    session_name = data.get('session_name', '').strip()
    if not session_name:
        return {"status": "error", "error": "Session name is required"}
    
    session_dir = safe_session_dir(session_name)
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        current_session_name = session_name
        print(f"[SESSION] Created session folder: {session_dir}")
        return {"status": "ok", "session_path": str(session_dir)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post('/session/resume')
async def upload_session_resume(file: UploadFile = File(...), session_name: str = Form(...)):
    """Upload resume to a specific session folder"""
    global profile_cache, current_session_name
    
    try:
        filename = safe_upload_name(file.filename)
        session_dir = safe_session_dir(session_name)
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Save resume file to session folder
        resume_path = session_dir / filename
        content = await file.read()
        resume_path.write_bytes(content)
        print(f"[SESSION] Resume saved to: {resume_path}")
        
        # Extract text from docx
        from docx import Document
        from io import BytesIO
        doc = Document(BytesIO(content))
        text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        
        current_session_name = session_name
        
        # Also update profile cache for AI responses
        if profile_cache is None:
            profile_cache = {}
        profile_cache['resume_text'] = text
        
        return {"status": "ok", "resume_text": text, "resume_path": str(resume_path)}
    except Exception as e:
        print(f"[SESSION RESUME ERROR] {e}")
        return {"status": "error", "error": str(e)}


@app.post('/session/save')
async def save_session_data(data: Dict[str, Any]):
    """Save session metadata (job description, API key, etc.)"""
    global profile_cache, current_session_name
    
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
        
        # Update profile cache for AI ONLY if the key provided is valid
        new_key = data.get('openai_api_key', '').strip()
        if new_key.startswith("sk-") and not new_key.endswith("KiwA"):
            if profile_cache is None:
                profile_cache = {}
            profile_cache['openai_api_key'] = new_key
            profile_cache['job_description'] = data.get('job_description', '')
            profile_cache['resume_text'] = data.get('resume_text', '')
            profile_cache['is_esl'] = data.get('is_esl', False)
            profile_cache['short_responses'] = data.get('short_responses', False)
            
            # Also save to profile for persistence
            save_profile(profile_cache)
        else:
            print(f"[SESSION] Skipping global API key update (provided key is empty or placeholder)")
        
        current_session_name = session_name
        
        return {"status": "ok", "session_path": str(session_dir)}
    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")
        return {"status": "error", "error": str(e)}


@app.post('/session/conversation')
async def save_conversation_entry(data: Dict[str, Any]):
    """Save a conversation entry (question + response) to the session"""
    global current_session_name
    
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


@app.post('/session/end')
async def end_session(data: Dict[str, str]):
    """Finalize and close a session"""
    global current_session_name

    session_name = data.get('session_name') or current_session_name
    if not session_name:
        return {"status": "ok", "message": "No session to end"}

    try:
        # Q&A pairs are already written to conversation.json as each answer
        # completes, so there is nothing left to append here.
        if not is_licensed_backend:
            end_demo()

        current_session_name = None
        reset_conversation_context()
        print(f"[SESSION] Ended session: {session_name} (history and rolling summary cleared)")
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
    """Load a previous session's data"""
    global current_session_name, profile_cache, session_usage
    try:
        session_dir = safe_session_dir(session_name)
        session_file = session_dir / 'session.json'
        
        if not session_file.exists():
            return {"status": "error", "error": "Session not found"}
        
        data = json.loads(session_file.read_text(encoding='utf-8'))
        session_key = (data.pop('openai_api_key', '') or '').strip()
        if session_key:
            # Older versions saved the key in plain text per session - remove it
            session_file.write_text(json.dumps(data, indent=2), encoding='utf-8')

        demo_error = start_demo()
        if demo_error:
            return {"status": "error", "error": demo_error}
        
        # Load conversation history
        conv_file = session_dir / 'conversation.json'
        history = []
        if conv_file.exists():
            try:
                history = json.loads(conv_file.read_text(encoding='utf-8'))
            except:
                history = []

        # Set current session so new conversations are saved here
        current_session_name = session_name
        print(f"[SESSION] Set active session to: {session_name}")

        # Reset session usage so API cost starts at $0 for this run
        session_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_cost": 0,
            "request_count": 0
        }

        # Restore profile cache for AI context
        # 1. Start with the currently validated global key
        current_valid_key = (profile_cache or {}).get('openai_api_key') or load_profile().get('openai_api_key', '')
        
        if profile_cache is None:
            profile_cache = {}
        profile_cache['job_description'] = data.get('job_description', '')
        profile_cache['resume_text'] = data.get('resume_text', '')
        profile_cache['target_role'] = data.get('target_role', '')
        profile_cache['target_language'] = data.get('target_language', '')
        
        # 2. Restore API key: Prefer the currently validated global key
        if current_valid_key:
            profile_cache['openai_api_key'] = current_valid_key
            print(f"[SESSION] Using current global API key (Session key was ignored)")
        elif session_key.startswith("sk-") and not session_key.endswith("KiwA"):
            profile_cache['openai_api_key'] = session_key
            print(f"[SESSION] API key restored from session '{session_name}'")
        else:
            print(f"[SESSION] WARNING: No API key available - user must re-enter key")
        
        # PERSIST: Ensure the AI endpoints (which reload from disk) see this restored context
        save_profile(profile_cache)

        return {
            "status": "ok",
            "session_name": session_name,
            "resume_text": data.get('resume_text', ''),
            "job_description": data.get('job_description', ''),
            "target_role": data.get('target_role', ''),
            "target_language": data.get('target_language', ''),
            "created_at": data.get('created_at', ''),
            "text_model": data.get('text_model', DEFAULT_TEXT_MODEL),
            "history": history
        }
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
    print("[CONVERSATION] History and rolling summary cleared - starting fresh session")
    return {"status": "ok", "message": "Conversation history cleared"}


@app.get('/conversation/history')
async def get_conversation_history():
    """Get current conversation history (for debugging)"""
    return {"history": conversation_history, "count": len(conversation_history)}


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

@app.post('/profile/resume')
async def upload_resume(file: UploadFile = File(...)):
    global profile_cache
    try:
        filename = safe_upload_name(file.filename)

        resumes_dir = BASE_DIR / 'resumes'
        print(f"Creating resumes directory at: {resumes_dir}")
        resumes_dir.mkdir(parents=True, exist_ok=True)
        print(f"Directory created: {resumes_dir.exists()}")
        out_path = resumes_dir / filename
        content = await file.read()
        out_path.write_bytes(content)

        # Extract text using python-docx (if available)
        Document = _docx_document()
        if Document is None:
            return {"status": "error", "error": "python-docx is not installed on the server. Install with: pip install python-docx"}

        try:
            doc = Document(out_path)
            text = "\n\n".join([p.text for p in doc.paragraphs if p.text and p.text.strip()])
        except Exception as e:
            return {"status": "error", "error": f"docx parse failed: {e}"}

        # Save extracted resume text into profile
        if not isinstance(profile_cache, dict):
            profile_cache = {}
        profile_cache['resume_text'] = text
        
        try:
            save_profile(profile_cache)
            # Invalidate the cached system context so the new resume is picked up
            invalidate_context_cache()
            print(f"\n{'='*60}")
            print(f"[RESUME UPLOAD SUCCESS]")
            print(f"File: {filename}")
            print(f"Text extracted: {len(text)} characters")
            print(f"Saved to profile! Context cache invalidated.")
            print(f"{'='*60}\n")
        except Exception as save_error:
            print(f"\n[RESUME SAVE FAILED]: {save_error}\n")
            return {"status": "error", "error": f"Failed to save resume: {save_error}"}

        return {"status": "ok", "resume_snippet": text[:800]}
    except Exception as e:
        print(f"\n[RESUME UPLOAD ERROR]: {e}\n")
        return {"status": "error", "error": str(e)}

# ----------------------------------------------------------------------------

# ============ SMART INTERVIEW ============
SMART_INTERVIEW_INSTRUCTIONS = (
    "SMART INTERVIEW MODE: the user message is a live exchange transcribed from a call, "
    "labeled by speaker. 'Interviewer:' lines come from the interviewer; 'Me:' lines are "
    "the candidate you are helping. Write what the candidate should say next in answer to "
    "the interviewer's latest question or task. If the candidate asked a clarifying question "
    "and the interviewer answered it, follow that clarification exactly. Never answer the "
    "candidate's own clarifying questions. If the interviewer is clarifying or changing a "
    "question you already answered earlier in this conversation, give the revised answer. "
    "Transcripts may contain small speech-to-text errors; infer the intended words. "
    "A 'Me (just said):' line is the end of what the candidate said right before; use it only as context. "
    "Reply with only what the candidate should say: never start with 'Me:' or any speaker label."
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
        "still explaining before asking. Reply with exactly YES or NO."
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
        verdict = (res.choices[0].message.content or "").strip().upper()
        print(f"[SMART] classify -> {verdict}")
        return {"answer_now": verdict.startswith("Y")}
    except Exception as e:
        print(f"[SMART] classify error: {e}")
        return {"answer_now": False}


@app.post("/ai/stream")
async def stream_ai_response(req: AIRequest):
    """Streaming endpoint for real-time AI responses using Server-Sent Events"""
    global conversation_history
    
    async def generate_stream():
        global conversation_history, conversation_summary
        if not check_access_allowed():
            yield f"data: {json.dumps({'error': 'Demo expired. Please purchase a license to continue.'})}\n\n"
            return

        try:
            client = get_async_client()
            
            current_profile = load_profile()
            resume_text = ""
            job_description = ""
            profile_metadata = None
            if current_profile and isinstance(current_profile, dict):
                resume_text = current_profile.get('resume_text') or ""
                job_description = current_profile.get('job_description') or ""
                profile_metadata = {k: v for k, v in current_profile.items() if k not in ['resume_text', 'job_description']}
            
            has_resume = bool(resume_text.strip())
            print(f"[STREAM] Has resume: {has_resume}, history len: {len(conversation_history)}")

            # Use cached system context (resume + JD baked in)
            is_esl = False
            short_responses = False
            if profile_metadata:
                is_esl = profile_metadata.get('is_esl', False)
                short_responses = profile_metadata.get('short_responses', False)

            system_content = get_system_context(
                req.role, req.target_language or 'Python',
                resume_text, job_description,
                for_vision=bool(req.screenshot),
                is_esl=is_esl,
                short_responses=short_responses
            )
            messages = [{"role": "system", "content": system_content}]
            if req.smart_mode:
                messages.append({"role": "system", "content": SMART_INTERVIEW_INSTRUCTIONS})

            # Inject rolling summary if available — compressed memory of evicted turns
            if conversation_summary:
                messages.append({
                    "role": "system",
                    "content": f"[CONTEXT FROM EARLIER IN THIS SESSION]:\n{conversation_summary}"
                })

            # Send last 3 raw turns (6 messages) for full-fidelity recent context
            messages.extend(conversation_history[-6:])

            if req.screenshot:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": req.transcript},
                        {"type": "image_url", "image_url": {"url": req.screenshot}}
                    ]
                })
                model = DEFAULT_SCREENSHOT_MODEL
                print(f"[STREAM] Using model: {model} (vision)")
            else:
                messages.append({"role": "user", "content": req.transcript})
                model = req.text_model if req.text_model and req.text_model in AVAILABLE_TEXT_MODELS else DEFAULT_TEXT_MODEL
                print(f"[STREAM] Using model: {model} (text-only, user selected: {req.text_model})")


            # GPT-5+ models are reasoning models: they use tokens for internal thinking
            # before producing output so they need a much higher token limit.
            # Do NOT pass temperature or max_tokens to reasoning models - unsupported params.
            token_param = {}
            if model.startswith("gpt-5"):
                token_param["max_completion_tokens"] = 16384  # reasoning needs headroom for thinking tokens
            else:
                token_param["max_tokens"] = 2048
                token_param["temperature"] = 0.7
            
            # Send heartbeat to establish SSE connection
            yield f"data: {json.dumps({'heartbeat': True})}\n\n"
            
            import time as _time
            _start_time = _time.time()
            
            # Create completion - catch errors separately so they always reach the client
            try:
                completion = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                    **token_param
                )
            except Exception as create_err:
                print(f"[STREAM] OpenAI create() error: {create_err}")
                err_text = str(create_err)
                if "insufficient_quota" in err_text:
                    err_text = "OUT_OF_CREDITS: Your OpenAI account is out of credits."
                yield f"data: {json.dumps({'error': err_text})}\n\n"
                return
            
            # Collect full response for history
            full_response = ""
            _ttft = 0  # time to first token
            
            # Yield chunks as they arrive - wrap in try/except for iteration errors
            try:
                async for chunk in completion:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        if not full_response:  # First token
                            _ttft = _time.time() - _start_time
                        full_response += content
                        # Send as Server-Sent Event format
                        yield f"data: {json.dumps({'chunk': content})}\n\n"
            except Exception as iter_err:
                err_msg = str(iter_err)[:200]
                print(f"[STREAM] Iteration error: {iter_err}")
                yield f"data: {json.dumps({'error': err_msg})}\n\n"
                return
            
            # Check for empty response
            if not full_response.strip():
                print(f"[STREAM] WARNING: Model {model} returned empty response")
                yield f"data: {json.dumps({'error': f'Model {model} returned an empty response. The model may not support this request format.'})}\n\n"
                return

            # Calculate usage and per-response cost BEFORE saving
            input_text = "\n".join([m.get('content', '') if isinstance(m.get('content'), str) else str(m.get('content', '')) for m in messages])
            input_tokens = count_tokens(input_text)
            output_tokens = count_tokens(full_response)
            
            # Estimate image tokens if screenshot was used
            image_tokens = 0
            if req.screenshot:
                image_tokens = estimate_image_tokens(req.screenshot, model)
            
            response_cost = calculate_cost(input_tokens, output_tokens, model, image_tokens)

            # Save to conversation history only if save_to_context is True
            # (skip for one-shot LeetCode problems, save for scenarios needing follow-up)
            save_to_context = req.save_to_context is not False
            if save_to_context:
                if req.screenshot:
                    user_msg = f"[USER SHARED A SCREENSHOT] Question about the screenshot: {req.transcript}"
                else:
                    user_msg = req.transcript
                conversation_history.append({"role": "user", "content": user_msg})
                conversation_history.append({"role": "assistant", "content": full_response})
                
                # Save to session folder if active
                if current_session_name:
                    try:
                        _total_time_current = _time.time() - _start_time
                        save_conversation_to_session(user_msg, full_response, bool(req.screenshot), model, response_time=_ttft, total_time=_total_time_current, cost=response_cost, input_tokens=input_tokens, output_tokens=output_tokens)
                    except Exception as save_err:
                        print(f"[SESSION SAVE ERROR] {save_err}")
                
                evict_old_turns()
                
                print(f"[STREAM] Conversation history: {len(conversation_history)} msgs | Summary: {len(conversation_summary)} chars")
            else:
                print(f"[STREAM] Skipped saving to history (save_to_context=False)")
            
            update_usage(input_tokens, output_tokens, model, image_tokens)
            
            _total_time = _time.time() - _start_time
            # Send completion signal with usage info and per-response cost
            yield f"data: {json.dumps({'done': True, 'model': model, 'usage': session_usage, 'response_in_tokens': input_tokens, 'response_out_tokens': output_tokens, 'response_cost': round(response_cost, 6), 'ttft': round(_ttft, 2), 'total_time': round(_total_time, 2)})}\n\n"
            
        except Exception as e:
            err_msg = str(e)[:200]
            print(f"Streaming AI Error: {e}")
            yield f"data: {json.dumps({'error': err_msg})}\n\n"
    
    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@app.post("/ai")
async def generate_ai_response(req: AIRequest):
    if not check_access_allowed():
        return {"answer": "Error: Demo expired. Please purchase a license to continue."}

    global conversation_history, conversation_summary
    print(f"\n[DEBUG] /ai called with: transcript={req.transcript[:50] if req.transcript else None}..., role={req.role}, screenshot={'YES' if req.screenshot else 'NO'}, save_to_context={req.save_to_context}")
    try:
        client = get_async_client()
        
        current_profile = load_profile()
        
        resume_text = ""
        job_description = ""
        if current_profile and isinstance(current_profile, dict):
            resume_text = current_profile.get('resume_text') or ""
            job_description = current_profile.get('job_description') or ""
        
        has_resume = bool(resume_text.strip())
        print(f"[AI] Has resume: {has_resume}, history len: {len(conversation_history)}")

        is_esl = False
        short_responses = False
        if current_profile and isinstance(current_profile, dict):
            is_esl = current_profile.get('is_esl', False)
            short_responses = current_profile.get('short_responses', False)

        # Use cached system context (resume + JD baked in) — same optimization as /ai/stream
        system_content = get_system_context(
            req.role, req.target_language or 'Python',
            resume_text, job_description,
            for_vision=bool(req.screenshot),
            is_esl=is_esl,
            short_responses=short_responses
        )
        messages = [{"role": "system", "content": system_content}]

        # Inject rolling summary if available
        if conversation_summary:
            messages.append({"role": "system", "content": f"[CONTEXT FROM EARLIER IN THIS SESSION]:\n{conversation_summary}"})

        # Send last 3 raw turns (6 messages) for full-fidelity recent context
        messages.extend(conversation_history[-6:])

        if req.screenshot:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": req.transcript},
                    {"type": "image_url", "image_url": {"url": req.screenshot}}
                ]
            })
            model = DEFAULT_SCREENSHOT_MODEL
        else:
            messages.append({"role": "user", "content": req.transcript})
            model = req.text_model if req.text_model and req.text_model in AVAILABLE_TEXT_MODELS else DEFAULT_TEXT_MODEL
        
        # GPT-5+ models are reasoning models: they need higher token limit for thinking + output
        token_param = {}
        if model.startswith("gpt-5"):
            token_param["max_completion_tokens"] = 4096
        else:
            token_param["max_tokens"] = 2048
            token_param["temperature"] = 0.7
        
        import time as _time
        _start_time = _time.time()
        
        completion = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **token_param
        )
        
        full_response = ""
        _ttft = 0
        async for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                if not full_response:  # First token
                    _ttft = _time.time() - _start_time
                full_response += chunk.choices[0].delta.content
                
        _total_time = _time.time() - _start_time
        
        # Calculate per-response cost
        input_text = "\n".join([m.get('content', '') if isinstance(m.get('content'), str) else str(m.get('content', '')) for m in messages])
        _input_tokens = count_tokens(input_text)
        _output_tokens = count_tokens(full_response)
        _image_tokens = estimate_image_tokens(req.screenshot, model) if req.screenshot else 0
        _response_cost = calculate_cost(_input_tokens, _output_tokens, model, _image_tokens)
        update_usage(_input_tokens, _output_tokens, model, _image_tokens)
        
        # Save to conversation history only if save_to_context is True
        # (skip for one-shot LeetCode problems, save for scenarios needing follow-up)
        save_to_context = req.save_to_context is not False
        if save_to_context:
            if req.screenshot:
                user_msg = f"[USER SHARED A SCREENSHOT] Question about the screenshot: {req.transcript}"
            else:
                user_msg = req.transcript
            conversation_history.append({"role": "user", "content": user_msg})
            conversation_history.append({"role": "assistant", "content": full_response})
            
            # Save to session folder if active
            if current_session_name:
                try:
                    save_conversation_to_session(user_msg, full_response, bool(req.screenshot), model, response_time=round(_ttft, 1), total_time=round(_total_time, 1), cost=_response_cost, input_tokens=_input_tokens, output_tokens=_output_tokens)
                except Exception as save_err:
                    print(f"[SESSION SAVE ERROR] {save_err}")
            
            evict_old_turns()
            
            print(f"[AI] Conversation history: {len(conversation_history)} msgs | Summary: {len(conversation_summary)} chars")
        else:
            print(f"[AI] Skipped saving to history (save_to_context=False)")
        
        print(f"[AI] Conversation history now has {len(conversation_history)} messages")
        
        return {
            "answer": full_response,
            "usage": session_usage,
            "response_in_tokens": _input_tokens,
            "response_out_tokens": _output_tokens,
            "response_cost": round(_response_cost, 6)
        }
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return {"answer": f"Error: {str(e)}"}


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