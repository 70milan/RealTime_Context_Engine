"""Session endpoints: create, save, load, resume, end, delete, and the conversation log."""
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
from fastapi import APIRouter, File, UploadFile, Form
from . import context, memory, session_store, usage
from .config import *
from .documents import _docx_text
from .session_store import safe_session_dir, safe_upload_name
from .user_profile import _profile, save_profile
from .context import set_active_context, clear_active_context
from .memory import reset_conversation_context

router = APIRouter()



@router.post('/session/create')
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


@router.post('/session/resume')
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

@router.post('/session/save')
async def save_session_data(data: Dict[str, Any]):
    """Save a new session's settings and make it the active session"""
    
    session_name = data.get('session_name', '').strip()
    if not session_name:
        return {"status": "error", "error": "Session name is required"}
    
    session_dir = safe_session_dir(session_name)
    session_dir.mkdir(parents=True, exist_ok=True)
    

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
            'mode': 'practice' if data.get('mode') == 'practice' else 'live',
            'practice_focus': data.get('practice_focus', 'mixed'),
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


@router.post('/session/conversation')
async def save_conversation_entry(data: Dict[str, Any]):
    """Save a conversation entry (question + response) to the session"""
    
    session_name = data.get('session_name') or session_store.current_session_name
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


@router.post('/session/said')
async def save_said(data: Dict[str, Any]):
    """Answer Review: attach what the candidate actually said to the last saved answer"""
    session_name = data.get('session_name') or session_store.current_session_name
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

@router.post('/session/end')
async def end_session(data: Dict[str, str]):
    """Finalize and close a session"""

    session_name = data.get('session_name') or session_store.current_session_name
    if not session_name:
        return {"status": "ok", "message": "No session to end"}

    try:
        # Q&A pairs are already written to conversation.json as each answer
        # completes, so there is nothing left to append here.
        clear_active_context()
        print(f"[SESSION] Ended session: {session_name} (context and conversation memory cleared)")
        return {"status": "ok", "message": f"Session '{session_name}' ended"}

    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get('/sessions')
async def list_sessions():
    """List all available sessions"""
    try:
        if not session_store.SESSIONS_DIR.exists():
            return {"sessions": []}
        
        sessions = []
        for session_dir in session_store.SESSIONS_DIR.iterdir():
            if session_dir.is_dir():
                session_file = session_dir / 'session.json'
                if session_file.exists():
                    data = json.loads(session_file.read_text(encoding='utf-8'))
                    sessions.append({
                        'name': session_dir.name,
                        'created_at': data.get('created_at', ''),
                        'target_role': data.get('target_role', ''),
                        'target_language': data.get('target_language', ''),
                        'job_description_preview': data.get('job_description', '')[:100],
                        'mode': data.get('mode', 'live')
                    })
        
        # Sort sessions by created_at descending (newest first)
        sessions.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return {"sessions": sessions}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@router.get('/session/load/{session_name}')
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
            "mode": data.get('mode', 'live'),
            "practice_focus": data.get('practice_focus', 'mixed'),
            "review": review_file.read_text(encoding='utf-8') if review_file.exists() else '',
            "history": history
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post('/session/activate')
async def activate_session(data: Dict[str, str]):
    """Resume a saved session: its resume/brief/JD/modes become the answer context, with a fresh
    conversation memory (earlier answers stay in the session file, not in the prompt)"""
    try:
        session_name = (data.get('session_name') or '').strip()
        session_file = safe_session_dir(session_name) / 'session.json'
        if not session_file.exists():
            return {"status": "error", "error": "Session not found"}
        set_active_context(session_name, json.loads(session_file.read_text(encoding='utf-8')))
        usage.reset_totals()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.delete('/session/delete/{session_name}')
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

@router.post('/conversation/clear')
async def clear_conversation():
    """Clear conversation history to start a fresh session"""
    reset_conversation_context()
    print("[CONVERSATION] Conversation memory cleared")
    return {"status": "ok", "message": "Conversation history cleared"}


@router.get('/conversation/history')
async def get_conversation_history():
    """Get current conversation history (for debugging)"""
    return {"history": memory.conversation_history, "notes": memory.conversation_notes, "count": len(memory.conversation_history)}
