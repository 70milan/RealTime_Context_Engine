"""Settings endpoints: models, profile, OpenAI key check, usage."""
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
from fastapi import APIRouter
from . import usage, user_profile
from .config import *
from .user_profile import _profile, save_profile

router = APIRouter()



@router.get('/models')
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

@router.get('/profile')
async def get_profile():
    # Never return secrets over HTTP - the UI doesn't need them back
    return {k: v for k, v in _profile().items() if k not in ('openai_api_key', 'groq_api_key')}

@router.post('/validate-api-key')
async def validate_api_key(data: Dict[str, str]):
    """Validate OpenAI API key before allowing session creation"""
    api_key = data.get('api_key', '').strip()
    
    if not api_key:
        return {"valid": False, "error": "API key is required"}
    
    if not api_key.startswith('sk-'):
        return {"valid": False, "error": "Invalid API key format"}
    
    try:
        from openai import AsyncOpenAI
        await AsyncOpenAI(api_key=api_key).models.list()
        # Store key immediately on successful validation
        _profile()['openai_api_key'] = api_key
        save_profile(_profile())
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

@router.get('/usage')
async def get_usage():
    """Get current session API usage and cost"""
    return usage.session_usage


@router.post('/usage/reset')
async def reset_usage():
    """Reset usage counters"""
    usage.reset_totals()
    return {"status": "ok", "message": "Usage reset"}
