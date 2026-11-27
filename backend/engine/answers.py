"""Answers: Smart Interview question detection and the streamed answer (/ai/stream)."""
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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from . import context, memory, session_store
from .config import *
from .usage import *
from .user_profile import get_async_client
from .context import get_active_context, get_system_prompt, final_answer_rules
from .memory import record_turn
from .session_store import save_conversation_to_session

router = APIRouter()



class AIRequest(BaseModel):
    transcript: str = ""
    role: str = ""
    target_language: Optional[str] = None
    screenshot: Optional[str] = None
    job_description: Optional[str] = None
    save_to_context: Optional[bool] = True
    text_model: Optional[str] = None
    # Smart Interview: transcript is a speaker-labeled exchange (Interviewer / Me)
    smart_mode: Optional[bool] = False
    # What the session history should show as the question (Smart: just the
    # interviewer's question, not the full prompt sent to the model)
    display_question: Optional[str] = None

    model_config = {"extra": "ignore"}

# ============ SMART INTERVIEW ============
SMART_INTERVIEW_INSTRUCTIONS = (
    "SMART INTERVIEW MODE: the user message is a live exchange transcribed from a call, labeled by speaker: "
    "'Interviewer:' lines are the interviewer, 'Me:' lines are you, the candidate. Answer the interviewer's latest "
    "question or task. If you asked a clarifying question and the interviewer answered it, follow that clarification "
    "exactly; never answer your own clarifying questions. If the interviewer is clarifying or changing a question "
    "answered earlier, give the revised answer. A 'Me (just said):' line is the end of what you said right before; "
    "use it only as context. Transcripts contain speech-to-text errors; infer the intended words. "
    "Never start your reply with a speaker label."
)


class SmartClassifyRequest(BaseModel):
    exchange: str = ""
    previous_question: str = ""

    model_config = {"extra": "ignore"}


@router.post("/smart/classify")
async def smart_classify(req: SmartClassifyRequest):
    """Fast yes/no: should the candidate answer now? Used only for interviewer turns
    the client-side question heuristics can't decide."""
    if not req.exchange.strip():
        return {"answer_now": False}
    prompt = (
        "You watch a live job interview transcript. Decide whether the interviewer has just "
        "finished a question, task, or clarification that the candidate should respond to now. "
        "Answer NO for small talk, acknowledgements, an unfinished sentence, or the interviewer "
        "still explaining before asking. Question marks come from speech-to-text and are often wrong: "
        "judge from the words, not the punctuation. Reply with exactly YES or NO."
    )
    user = req.exchange.strip()[-2000:]
    if req.previous_question.strip():
        user = f"(Previously answered question: {req.previous_question.strip()[-500:]})\n\n{user}"
    try:
        client = get_async_client()
        res = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}],
            max_tokens=1,
            temperature=0,
        )
        track_completion_usage(res.usage, "gpt-4o-mini")
        verdict = (res.choices[0].message.content or "").strip().upper()
        print(f"[SMART] classify -> {verdict}")
        return {"answer_now": verdict.startswith("Y")}
    except Exception as e:
        print(f"[SMART] classify error: {e}")
        return {"answer_now": False}


@router.post("/ai/stream")
async def stream_ai_response(req: AIRequest):
    """Stream one answer as Server-Sent Events.

    What the model gets, in this order (fixed parts first, so OpenAI's prompt cache covers them):
      1. the session prompt: persona, rules, modes, brief or resume, JD     (get_system_prompt)
      2. Smart Interview instructions, when the question comes from Smart mode
      3. one line per older question, at most MAX_NOTES                    (conversation_notes)
      4. the last HISTORY_TURNS questions and answers verbatim             (conversation_history)
      5. final rules: truthfulness, screenshot, ESL/Cue format - read last, so they win
      6. the question (Smart: the labeled exchange), plus the screenshot
    """
    async def generate_stream():
        ctx = get_active_context()
        if not ctx:
            yield f"data: {json.dumps({'error': 'No active session. Create or resume a session first.'})}\n\n"
            return

        import time as _time
        try:
            client = get_async_client()
            messages = [{"role": "system", "content": get_system_prompt(ctx)}]
            if req.smart_mode:
                messages.append({"role": "system", "content": SMART_INTERVIEW_INSTRUCTIONS})
            if memory.conversation_notes:
                messages.append({"role": "system", "content": "Earlier in this interview (one line per question; "
                                 "stay consistent with what you said):\n" + "\n".join(memory.conversation_notes)})
            messages.extend(memory.conversation_history)
            messages.append(final_answer_rules(ctx, screenshot=bool(req.screenshot)))
            if req.screenshot:
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": req.transcript},
                    {"type": "image_url", "image_url": {"url": req.screenshot}},
                ]})
            else:
                messages.append({"role": "user", "content": req.transcript})

            # Screenshots use the selected model too: all of them read images, and coding
            # problems are where the stronger model matters most
            model = req.text_model if req.text_model in AVAILABLE_TEXT_MODELS else DEFAULT_TEXT_MODEL
            if model.startswith("gpt-5"):
                # Reasoning models: thinking tokens need headroom; temperature is unsupported
                token_param = {"max_completion_tokens": 16384}
            else:
                token_param = {"max_tokens": 2048, "temperature": 0.7}
            print(f"[STREAM] {model} | smart={req.smart_mode} screenshot={bool(req.screenshot)} | "
                  f"notes={len(memory.conversation_notes)} history={len(memory.conversation_history) // 2} turns")

            yield f"data: {json.dumps({'heartbeat': True})}\n\n"
            _start_time = _time.time()
            try:
                # prompt_cache_key routes every answer of this session to the same OpenAI cache,
                # so the fixed session prompt is billed at the cached rate after the first answer
                completion = await client.chat.completions.create(
                    model=model, messages=messages, stream=True,
                    stream_options={"include_usage": True},
                    prompt_cache_key=context.prompt_cache_key(), **token_param)
            except Exception as create_err:
                print(f"[STREAM] OpenAI create() error: {create_err}")
                err_text = str(create_err)
                if "insufficient_quota" in err_text:
                    err_text = "OUT_OF_CREDITS: Your OpenAI account is out of credits."
                yield f"data: {json.dumps({'error': err_text})}\n\n"
                return

            full_response = ""
            _ttft = 0
            usage = None
            try:
                async for chunk in completion:
                    if chunk.usage:
                        usage = chunk.usage  # last chunk: real token counts, incl. cached
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        if not full_response:
                            _ttft = _time.time() - _start_time
                        full_response += content
                        yield f"data: {json.dumps({'chunk': content})}\n\n"
            except Exception as iter_err:
                print(f"[STREAM] Iteration error: {iter_err}")
                yield f"data: {json.dumps({'error': str(iter_err)[:200]})}\n\n"
                return

            if not full_response.strip():
                print(f"[STREAM] WARNING: Model {model} returned empty response")
                yield f"data: {json.dumps({'error': f'Model {model} returned an empty response. The model may not support this request format.'})}\n\n"
                return

            # Cost from OpenAI's own counts; a local estimate only if they're missing
            if usage:
                details = getattr(usage, 'prompt_tokens_details', None)
                cached_tokens = (getattr(details, 'cached_tokens', 0) or 0) if details else 0
                input_tokens, output_tokens, image_tokens = usage.prompt_tokens, usage.completion_tokens, 0
            else:
                input_tokens = count_tokens("\n".join(m['content'] if isinstance(m['content'], str) else req.transcript for m in messages))
                output_tokens = count_tokens(full_response)
                image_tokens = estimate_image_tokens(req.screenshot, model) if req.screenshot else 0
                cached_tokens = 0
            response_cost = update_usage(input_tokens, output_tokens, model, image_tokens, cached_tokens)
            _total_time = _time.time() - _start_time

            # Memory gets the question as asked (Smart: the interviewer's question, without the
            # "Me (just said)" context that only mattered for this answer)
            question = (req.display_question or req.transcript).strip()
            if req.screenshot:
                question = f"[Screenshot] {question}"
            if req.save_to_context is not False:
                record_turn(question, full_response)
            if session_store.current_session_name:
                try:
                    save_conversation_to_session(question, full_response, bool(req.screenshot), model,
                                                 response_time=_ttft, total_time=_total_time, cost=response_cost,
                                                 input_tokens=input_tokens, output_tokens=output_tokens)
                except Exception as save_err:
                    print(f"[SESSION SAVE ERROR] {save_err}")

            yield f"data: {json.dumps({'done': True, 'model': model, 'usage': session_usage, 'response_in_tokens': input_tokens, 'response_cached_tokens': cached_tokens, 'response_out_tokens': output_tokens, 'response_cost': round(response_cost, 6), 'ttft': round(_ttft, 2), 'total_time': round(_total_time, 2)})}\n\n"

        except Exception as e:
            print(f"Streaming AI Error: {e}")
            yield f"data: {json.dumps({'error': str(e)[:200]})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
