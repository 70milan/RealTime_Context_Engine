"""Practice mode: questions, follow-ups, hints, the interviewer's voice, answer transcription."""
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
from fastapi import APIRouter, File, UploadFile
from . import session_store
from .config import *
from .usage import track_completion_usage, _add_transcription_usage
from .user_profile import _profile, save_profile, get_async_client
from .context import get_active_context, get_system_prompt, final_answer_rules
from .session_store import safe_session_dir

router = APIRouter()



# ============ PRACTICE MODE ============
# A mock interview on the same screen as a live one: the app asks generated questions
# out loud, listens to the answer, sometimes follows up, and critiques the round.
# With a Groq key (free tier) the questions, follow-ups, hints and answer transcription
# run on Groq; without one they fall back to the OpenAI key. The critique always uses gpt-4o.
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_TEXT_MODEL = "openai/gpt-oss-120b"
GROQ_STT_MODEL = "whisper-large-v3-turbo"
PRACTICE_VOICE = "en-IN-PrabhatNeural"
PRACTICE_VOICE_RATE = "+15%"  # interviewer speaks at 1.15x
PRACTICE_DIR = BASE_DIR / 'practice'
_groq_clients: Dict[str, "AsyncOpenAI"] = {}

PRACTICE_ROUNDS = {  # focus -> (main questions, coding questions)
    'mixed': (7, 2), 'behavioural': (7, 1), 'technical': (7, 2), 'coding': (2, 5),
}
PRACTICE_FOCUS_TEXT = {
    'mixed': "a realistic mix: start with their current role, then technical deep-dives on their real projects and the JD's required skills, one or two behavioural questions",
    'behavioural': "behavioural and situational questions (conflict, ownership, failure, stakeholders, prioritising), each anchored in their real projects",
    'technical': "technical deep-dives: how their pipelines actually worked, design choices, tools the JD requires, troubleshooting and performance",
    'coding': "concepts and approach questions around the coding tasks (complexity, trade-offs, testing)",
}

def get_groq_key() -> Optional[str]:
    key = (_profile().get('groq_api_key') or '').strip()
    return key or None

def _groq_client(key: str) -> "AsyncOpenAI":
    from openai import AsyncOpenAI
    client = _groq_clients.get(key)
    if client is None:
        _groq_clients.clear()
        client = _groq_clients[key] = AsyncOpenAI(api_key=key, base_url=GROQ_BASE_URL)
    return client

async def practice_complete(system: str, user: str, max_tokens: int = 800) -> str:
    """One practice-mode model call: Groq's gpt-oss-120b when there's a Groq key, else gpt-4o-mini"""
    key = get_groq_key()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if key:
        # gpt-oss is a reasoning model: low effort keeps it fast; its thinking needs token headroom
        res = await _groq_client(key).chat.completions.create(
            model=GROQ_TEXT_MODEL, messages=messages, reasoning_effort="low",
            max_completion_tokens=max_tokens + 1500)
        print(f"[PRACTICE] groq {GROQ_TEXT_MODEL}: {res.usage.prompt_tokens if res.usage else '?'} in")
    else:
        res = await get_async_client().chat.completions.create(
            model="gpt-4o-mini", messages=messages, max_tokens=max_tokens, temperature=0.7)
        track_completion_usage(res.usage, "gpt-4o-mini")
    return (res.choices[0].message.content or "").strip()

def _practice_background(ctx: Dict[str, Any], limit: int = 12000) -> str:
    """The candidate's experience for practice prompts: the brief if there is one, else the resume"""
    text = (ctx.get('talking_points') or '').strip() or (ctx.get('resume_text') or '').strip()
    return text[:limit]

def _asked_file(ctx: Dict[str, Any]) -> Path:
    """Asked questions are remembered per job description, so a new JD starts fresh"""
    import hashlib
    jd = " ".join((ctx.get('job_description') or '').lower().split())
    return PRACTICE_DIR / (hashlib.sha256(jd.encode('utf-8')).hexdigest()[:16] + '.json')

def _load_asked(ctx: Dict[str, Any]) -> list:
    try:
        return json.loads(_asked_file(ctx).read_text(encoding='utf-8')).get('asked', [])
    except Exception:
        return []


@router.post('/validate-groq-key')
async def validate_groq_key(data: Dict[str, str]):
    """Check a Groq key and remember it (encrypted). An empty key removes the saved one."""
    key = (data.get('api_key') or '').strip()
    if not key:
        if _profile().pop('groq_api_key', None):
            save_profile(_profile())
        return {"valid": True, "cleared": True}
    try:
        await _groq_client(key).models.list()
    except Exception as e:
        msg = str(e)
        return {"valid": False, "error": "Invalid Groq API key" if "401" in msg or "invalid" in msg.lower() else f"Groq check failed: {msg[:120]}"}
    if _profile().get('groq_api_key') != key:
        _profile()['groq_api_key'] = key
        save_profile(_profile())
    return {"valid": True}


@router.get('/practice/status')
async def practice_status():
    """Which engine practice uses: Groq (free, answer text appears when you finish) or OpenAI (live text)"""
    return {"groq": bool(get_groq_key())}


PRACTICE_QUESTIONS_INSTRUCTIONS = (
    "You are an experienced interviewer for the role below, preparing one round of a mock interview for this "
    "candidate. Write {main} main questions and {code} coding questions.\n"
    "Main questions: {focus}. Ground them in the candidate's real experience and the job description: their "
    "actual projects and tools, the JD's required skills, and the gaps between the two. Word them the way an "
    "interviewer talks on a call (e.g. 'Okay, so walk me through...'), one or two sentences, in the order a real "
    "interview would go.\n"
    "Coding questions: short live-coding tasks this interviewer would give for this JD, in {language} or the "
    "JD's main languages (e.g. SQL, PySpark), solvable in 5-10 minutes, stated in one or two sentences with the "
    "table and column names needed.\n"
    "Never repeat or closely paraphrase anything in ALREADY ASKED.\n"
    "Output one question per line, starting with 'MAIN: ' or 'CODE: '. No numbering, no other text."
)


@router.post('/practice/questions')
async def practice_questions(data: Dict[str, Any]):
    """Generate the next round's questions. They count as asked from now on, so later rounds don't repeat them."""
    ctx = get_active_context()
    if not ctx:
        return {"status": "error", "error": "No active session"}
    focus = data.get('focus') if data.get('focus') in PRACTICE_ROUNDS else 'mixed'
    n_main, n_code = PRACTICE_ROUNDS[focus]
    asked = _load_asked(ctx)
    system = PRACTICE_QUESTIONS_INSTRUCTIONS.format(
        main=n_main, code=n_code, focus=PRACTICE_FOCUS_TEXT[focus],
        language=(ctx.get('target_language') or 'SQL').strip() or 'SQL')
    user = (f"ROLE: {ctx.get('target_role', '')}\n\n--- CANDIDATE ---\n{_practice_background(ctx)}\n\n"
            f"--- JOB DESCRIPTION ---\n{ctx.get('job_description', '')}\n\n"
            "--- ALREADY ASKED ---\n" + ("\n".join(asked[-150:]) or "(none)"))
    try:
        text = await practice_complete(system, user, max_tokens=1500)
    except Exception as e:
        print(f"[PRACTICE] questions error: {e}")
        return {"status": "error", "error": str(e)[:200]}
    questions = []
    for line in text.splitlines():
        line = line.strip().lstrip('-*0123456789. ').strip()
        for prefix, kind in (('MAIN:', 'main'), ('CODE:', 'coding')):
            if line.upper().startswith(prefix) and line[len(prefix):].strip():
                questions.append({"kind": kind, "text": line[len(prefix):].strip()})
    if not questions:
        return {"status": "error", "error": "Could not generate questions, try again"}
    PRACTICE_DIR.mkdir(parents=True, exist_ok=True)
    _asked_file(ctx).write_text(json.dumps({"asked": asked + [q['text'] for q in questions]}, indent=1), encoding='utf-8')
    print(f"[PRACTICE] Round questions: {len(questions)} ({focus}); {len(asked)} asked before for this JD")
    return {"status": "ok", "questions": questions}


PRACTICE_FOLLOWUP_INSTRUCTIONS = (
    "You are the interviewer in a mock interview. You get your question, the candidate's answer (speech-to-text, "
    "may have small errors) and their real background. Decide whether to ask ONE follow-up, the way a real "
    "interviewer drills in: when the answer was vague, skipped how something actually worked, made a claim worth "
    "probing (a tool, a number, an architecture), or does not match their background. Otherwise move on; about two "
    "of every three answers should move on. Reply with exactly NEXT to move on, or with only the follow-up question, "
    "spoken naturally in one or two sentences."
)


@router.post('/practice/next')
async def practice_next(data: Dict[str, Any]):
    """After an answer: a follow-up question, or '' to move on (one small call)"""
    ctx = get_active_context()
    if not ctx:
        return {"status": "error", "error": "No active session"}
    answer = (data.get('answer') or '').strip()
    code = (data.get('code') or '').strip()
    if not answer and not code:
        return {"status": "ok", "follow_up": ""}
    user = (f"--- CANDIDATE BACKGROUND ---\n{_practice_background(ctx, 6000)}\n\n"
            f"YOUR QUESTION: {data.get('question', '')}\n\nCANDIDATE ANSWER: {answer or '(no spoken answer)'}"
            + (f"\n\nCANDIDATE CODE:\n{code[:4000]}" if code else ""))
    try:
        text = await practice_complete(PRACTICE_FOLLOWUP_INSTRUCTIONS, user, max_tokens=120)
    except Exception as e:
        print(f"[PRACTICE] follow-up error: {e}")
        return {"status": "ok", "follow_up": ""}  # never block the round on this
    follow_up = "" if not text or text.strip().upper().startswith("NEXT") else text.strip().strip('"')
    return {"status": "ok", "follow_up": follow_up}


@router.post('/practice/hint')
async def practice_hint(data: Dict[str, Any]):
    """Cue bullets for a practice question (the Hints toggle). Not kept in any memory."""
    ctx = get_active_context()
    if not ctx:
        return {"status": "error", "error": "No active session"}
    cue_ctx = dict(ctx, short_responses=True)
    system = get_system_prompt(cue_ctx) + "\n\n" + final_answer_rules(cue_ctx)['content']
    try:
        hint = await practice_complete(system, f"Interviewer: {data.get('question', '')}", max_tokens=200)
        return {"status": "ok", "hint": hint}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


@router.post('/practice/tts')
async def practice_tts(data: Dict[str, Any]):
    """The interviewer's voice: Microsoft's free neural voices via edge-tts (needs internet).
    On failure the client falls back to the built-in Windows voice."""
    from fastapi.responses import Response
    text = (data.get('text') or '').strip()[:2000]
    if not text:
        return Response(status_code=400)
    try:
        import edge_tts
        audio = b""
        async for chunk in edge_tts.Communicate(text, data.get('voice') or PRACTICE_VOICE, rate=PRACTICE_VOICE_RATE).stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        print(f"[PRACTICE] tts error: {e}")
        return Response(status_code=502)


def _stt_prompt(ctx: Dict[str, Any]) -> str:
    """Vocabulary hint for Whisper: the acronyms and tool names in the resume and JD"""
    text = f"{ctx.get('resume_text', '')} {ctx.get('talking_points', '')} {ctx.get('job_description', '')}"
    words = re.findall(r"\b(?:[A-Z][A-Za-z0-9]*[A-Z0-9][A-Za-z0-9-]*|[A-Z]{2,}[a-z]*)\b", text)
    counts: Dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    top = sorted(counts, key=lambda w: -counts[w])[:45]
    return "Data engineering interview answer. Terms: " + ", ".join(top)


@router.post('/practice/transcribe')
async def practice_transcribe(file: UploadFile = File(...)):
    """Transcribe one recorded answer (WAV): Groq Whisper (free tier), else OpenAI"""
    ctx = get_active_context()
    audio = await file.read()
    seconds = max(0.0, (len(audio) - 44) / 32000)  # 16 kHz mono 16-bit
    try:
        key = get_groq_key()
        if key:
            res = await _groq_client(key).audio.transcriptions.create(
                model=GROQ_STT_MODEL, file=("answer.wav", audio, "audio/wav"),
                prompt=_stt_prompt(ctx or {}), language="en", temperature=0)
        else:
            res = await get_async_client().audio.transcriptions.create(
                model="gpt-4o-mini-transcribe", file=("answer.wav", audio, "audio/wav"), language="en")
            _add_transcription_usage(int(len(audio) * 1.5), "gpt-4o-mini-transcribe")  # 16 kHz WAV -> the 24 kHz byte basis
        text = (getattr(res, 'text', '') or '').strip()
        print(f"[PRACTICE] Transcribed {seconds:.1f}s of answer -> {len(text)} chars")
        return {"status": "ok", "text": text}
    except Exception as e:
        print(f"[PRACTICE] transcribe error: {e}")
        return {"status": "error", "error": str(e)[:200]}


@router.post('/practice/record')
async def practice_record(data: Dict[str, Any]):
    """Save one practice question and your answer to the session (Past Sessions, Critique)"""
    if not session_store.current_session_name:
        return {"status": "error", "error": "No active session"}
    from datetime import datetime
    conv_file = safe_session_dir(session_store.current_session_name) / 'conversation.json'
    try:
        conversation = json.loads(conv_file.read_text(encoding='utf-8')) if conv_file.exists() else []
        conversation.append({
            'timestamp': datetime.now().isoformat(),
            'question': (data.get('question') or '').strip(),
            'response': (data.get('hint') or '').strip(),
            'said': (data.get('said') or '').strip(),
            'code': (data.get('code') or '').strip(),
            'kind': data.get('kind') if data.get('kind') in ('main', 'followup', 'coding') else 'main',
            'number': int(data.get('number') or 0),
            'practice': True,
            'model': 'practice',
        })
        conv_file.write_text(json.dumps(conversation, indent=2), encoding='utf-8')
        return {"status": "ok", "count": len(conversation)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
