"""Conversation memory: the last questions verbatim plus one-line notes on older ones."""
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
from .usage import track_completion_usage
from .user_profile import get_api_key, get_async_client


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
