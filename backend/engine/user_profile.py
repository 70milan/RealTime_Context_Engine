"""The user profile on disk (API keys encrypted with Windows DPAPI) and the OpenAI client."""
import os
import sys
import json
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from openai import AsyncOpenAI
from .config import *


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
        groq_enc = data.pop('groq_api_key_enc', None)
        if groq_enc:
            try:
                data['groq_api_key'] = decrypt_secret(groq_enc)
            except Exception as e:
                print(f"[PROFILE] Could not decrypt Groq key: {e}")
        if not enc and data.get('openai_api_key'):
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
        for name in ('openai_api_key', 'groq_api_key'):
            key = data.pop(name, None)
            if key:
                data[name + '_enc'] = encrypt_secret(key)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        PROFILE_PATH.write_text(json_str, encoding="utf-8")
        print(f"[SAVE_PROFILE] Successfully wrote {len(json_str)} bytes to {PROFILE_PATH}")
    except Exception as e:
        print(f"[SAVE_PROFILE ERROR] Failed to save: {e}")
        raise  # Re-raise so caller knows it failed

profile_cache = load_profile()

def _profile() -> Dict[str, Any]:
    global profile_cache
    if not isinstance(profile_cache, dict):
        profile_cache = {}
    return profile_cache

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
