"""Talking Points brief (Generate) and the answer critique (Critique / end of a practice round)."""
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
from .config import *
from .documents import _docx_text
from .session_store import safe_session_dir
from .usage import track_completion_usage
from .user_profile import get_async_client

router = APIRouter()



BRIEF_INSTRUCTIONS = (
    "You prepare a job candidate for an interview. From their resume and the job description, write a brief "
    "that an interview assistant will use instead of the full resume. Plain text, no markdown headings or bold.\n\n"
    "RELEVANT EXPERIENCE\n"
    "For each employer that matters for this job: one line with role, company, dates, domain; then short bullets "
    "with the specifics that match the job description: tools, platforms, data types, volumes, numbers, and "
    "what the candidate personally owned. Keep every number and named technology that is relevant. Drop "
    "anything unrelated to this job.\n\n"
    "TALKING POINTS\n"
    "5-10 short bullets: which experience to lead with for this job's main requirements, the exact terms to use, "
    "and for each requirement the resume does not cover, how to answer honestly from adjacent experience.\n\n"
    "Each bullet must be concrete: what was built, with which tools, for which data, at what scale or result. "
    "Generic bullets like 'collaborated with stakeholders' are useless to the assistant; leave them out. "
    "Use only facts from the resume. Never invent employers, tools, numbers or projects. "
    "Attribute each tool and platform only to the employer whose resume section names it: if ADF appears under one job "
    "and not another, never list ADF under the other. Keep personal and certification projects labeled as such. "
    "Aim for 4000-6000 characters; never exceed 6000."
)


@router.post('/session/brief')
async def generate_session_brief(file: UploadFile = File(...), job_description: str = Form(...),
                                 target_role: str = Form(''), api_key: str = Form('')):
    """Draft the talking points for the setup screen: the resume condensed to what this JD needs, plus how to answer"""
    try:
        resume_text = _docx_text(await file.read())
        if not resume_text.strip():
            return {"status": "error", "error": "No text found in the resume"}
        if not job_description.strip():
            return {"status": "error", "error": "Paste the job description first"}

        # Once per session, and every answer builds on it: gpt-4o-mini kept moving tools
        # between employers here, so the stronger model is worth a few cents
        model = "gpt-4o"
        completion = await get_async_client(api_key.strip() or None).chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": BRIEF_INSTRUCTIONS},
                {"role": "user", "content": (
                    f"TARGET ROLE: {target_role.strip() or 'see job description'}\n\n"
                    f"--- JOB DESCRIPTION ---\n{job_description.strip()}\n\n"
                    f"--- RESUME ---\n{resume_text.strip()}"
                )},
            ],
            max_tokens=3000,
            temperature=0.2,
        )
        brief = (completion.choices[0].message.content or "").strip()
        track_completion_usage(completion.usage, model)
        print(f"[BRIEF] Generated {len(brief)} chars from a {len(resume_text)}-char resume")
        return {"status": "ok", "talking_points": brief}
    except Exception as e:
        print(f"[BRIEF ERROR] {e}")
        return {"status": "error", "error": str(e)}

CRITIQUE_INSTRUCTIONS = (
    "You are an interview coach reviewing a mock or real interview. For each question you get what the "
    "interviewer asked, the answer an assistant suggested, and what the candidate actually said (speech-to-text, "
    "may have small errors). The suggestions were written by an assistant and are often wrong about which job "
    "used which tool. The RESUME is the only source of truth: a tool or architecture counts for a job only if "
    "that job's own section of the resume names it (the skills list does not count).\n\n"
    "Write plain text, no markdown headings or bold. For each question:\n"
    "Q<n>: <the question in a few words>\n"
    "- Suggestion check: each claim in the suggestion that the resume does not support for that job, "
    "e.g. 'ADF at Acme - not in the Acme section'. Write 'ok' if there are none.\n"
    "- Verdict: Strong / OK / Weak, with a one-line reason.\n"
    "- Covered: the key points the candidate actually made.\n"
    "- Missed: points the candidate left out that the resume supports and the interviewer wanted. "
    "Never list anything from the Suggestion check.\n"
    "- Say next time: the exact one or two sentences to say, in first person, using only resume facts for that "
    "same job (tools, data, numbers). Not advice like 'I will elaborate'.\n"
    "If nothing was captured for a question, write only 'Q<n>: <question> - not captured' on one line. "
    "PRACTICE rounds have no suggestion (SUGGESTED: none): write 'Suggestion check: n/a' and judge what the "
    "candidate said against the resume and what a strong answer to that question needs. FOLLOW-UP questions "
    "belong to the main question before them. For a coding question, judge the CANDIDATE CODE: correctness, "
    "edge cases, complexity, and how well they explained it; 'Say next time' may be the corrected code.\n"
    "End with OVERALL: the 3 most important things to practise before the next interview."
)


@router.post('/session/critique/{session_name}')
async def critique_session(session_name: str, start: int = 0):
    """Answer Review: compare what was suggested with what the candidate said, per question.
    Runs when the user clicks Critique, or at the end of a practice round (start = the round's first
    entry, so only that round is reviewed). Saved as review.txt in the session; rounds are appended."""
    session_dir = safe_session_dir(session_name)
    try:
        session_file = session_dir / 'session.json'
        conv_file = session_dir / 'conversation.json'
        data = json.loads(session_file.read_text(encoding='utf-8')) if session_file.exists() else {}
        conversation = json.loads(conv_file.read_text(encoding='utf-8')) if conv_file.exists() else []
        conversation = conversation[max(0, start):]
        if not any(e.get('said') or e.get('code') for e in conversation):
            return {"status": "error", "error": "No recorded answers in this session. Your answers are saved in Smart mode from this version on."}

        parts = []
        for n, e in enumerate((e for e in conversation if e.get('question')), 1):
            kind = {'followup': ' (FOLLOW-UP)', 'coding': ' (CODING)'}.get(e.get('kind', ''), '')
            parts.append(f"Q{n}{kind} INTERVIEWER: {e['question'][:1500]}\n"
                         f"SUGGESTED: {(e.get('response') or 'none')[:2000]}\n"
                         f"CANDIDATE SAID: {e.get('said') or '(not captured)'}"
                         + (f"\nCANDIDATE CODE:\n{e['code'][:4000]}" if e.get('code') else ''))
        # The resume, not the generated brief: the brief can carry the same mistakes as the suggestions
        background = (data.get('resume_text') or data.get('talking_points') or '').strip()[:30000]
        user = (f"ROLE: {data.get('target_role', '')}\n\n--- CANDIDATE RESUME ---\n{background}\n\n"
                f"--- INTERVIEW ---\n" + "\n\n".join(parts))[-60000:]
        user += "\n\nReminder: check every suggestion against the job's own resume section before judging."

        # One call per click, so the stronger model is worth it (a few cents)
        model = "gpt-4o"
        completion = await get_async_client().chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": CRITIQUE_INSTRUCTIONS}, {"role": "user", "content": user}],
            max_tokens=4000,
            temperature=0.3,
        )
        review = (completion.choices[0].message.content or "").strip()
        track_completion_usage(completion.usage, model)
        review_file = session_dir / 'review.txt'
        if start > 0 and review_file.exists():
            from datetime import datetime
            review = (review_file.read_text(encoding='utf-8').rstrip()
                      + f"\n\n===== Round reviewed {datetime.now():%b %d %H:%M} =====\n" + review)
        review_file.write_text(review, encoding='utf-8')
        print(f"[REVIEW] Critique for '{session_name}': {len(review)} chars")
        return {"status": "ok", "review": review}
    except Exception as e:
        print(f"[REVIEW ERROR] {e}")
        return {"status": "error", "error": str(e)}
