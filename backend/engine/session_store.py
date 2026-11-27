"""Session folders on disk: names, paths, and the saved conversation of each session."""
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
from fastapi import HTTPException
from .config import *


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
