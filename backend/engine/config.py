"""Paths and model/price tables shared by the whole backend."""
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
    BASE_DIR = Path(__file__).resolve().parent.parent

# "cached" is the rate for prompt tokens OpenAI served from its prompt cache.
PRICING = {
    "gpt-3.5-turbo": {"input": 0.50, "cached": 0.50, "output": 1.50},
    "gpt-4o-mini": {"input": 0.15, "cached": 0.075, "output": 0.60},
    "gpt-4o": {"input": 2.50, "cached": 1.25, "output": 10.00},
    "gpt-5-nano": {"input": 0.05, "cached": 0.005, "output": 0.40},
    "gpt-5-mini": {"input": 0.25, "cached": 0.025, "output": 2.00},
}

import threading



# Available models for text-only responses (user can select)
AVAILABLE_TEXT_MODELS = {
    "gpt-3.5-turbo": {"name": "GPT-3.5 Turbo", "speed": "Fastest", "cost": "Cheapest", "accuracy": "Good", "desc": "Quick text answers"},
    "gpt-4o-mini": {"name": "GPT-4o Mini", "speed": "Fast", "cost": "Cheap", "accuracy": "Better", "desc": "Balanced option"},
    "gpt-4o": {"name": "GPT-4o", "speed": "Medium", "cost": "Moderate", "accuracy": "Great", "desc": "Complex questions"},
    "gpt-5-nano": {"name": "ChatGPT 5 Nano", "speed": "Ultrasonic", "cost": "Cheapest", "accuracy": "Decent", "desc": "Lightweight tasks"},
    "gpt-5-mini": {"name": "ChatGPT 5 Mini", "speed": "Blistering", "cost": "Cheap", "accuracy": "Solid", "desc": "Day-to-day tasks"}
}

DEFAULT_TEXT_MODEL = "gpt-4o-mini"
