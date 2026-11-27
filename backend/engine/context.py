"""The active session's context and the prompts every answer is built from."""
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
from . import memory, session_store, user_profile
from .user_profile import _profile, save_profile
from .session_store import safe_session_dir


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
    global active_context
    active_context = {k: (data.get(k) or default) for k, default in CONTEXT_FIELDS.items()}
    session_store.current_session_name = session_name
    memory.reset_conversation_context()
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
    global active_context
    active_context = {}
    session_store.current_session_name = None
    memory.reset_conversation_context()
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
    "If asked about something you used at a different job, say where (e.g. 'At my previous company I...'). "
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

def prompt_cache_key() -> str:
    """Same for every answer of a session: routes them to one OpenAI prompt cache"""
    return f"session-{(_cached_prompt_key or '')[:24]}"

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
    if ctx.get('short_responses'):
        # Cue lines are already short; ESL only needs plain words in them
        rules.append(CUE_RULES + (" Use plain, simple words in the cues." if ctx.get('is_esl') else ""))
    elif ctx.get('is_esl'):
        rules.append(ESL_RULES)
    return {"role": "system", "content": "\n\n".join(rules)}
