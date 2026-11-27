"""Token counting, prices and the running cost of the session (shown in the app)."""
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

def reset_totals():
    """Zero the session's usage (in place: other modules hold this same dict)"""
    session_usage.update({"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0, "request_count": 0,
                          "ai_cost": 0.0, "transcription_seconds": 0.0, "transcription_cost": 0.0})

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
