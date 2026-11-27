"""Live transcription: a WebSocket per audio source, relayed to OpenAI Realtime."""
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
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .security import ALLOWED_HOSTS, _token_ok
from .usage import _add_transcription_usage, TRANSCRIBE_MODEL, FALLBACK_TRANSCRIBE_MODEL
from .user_profile import get_api_key, _profile

router = APIRouter()



# Streaming transcription model: emits word-level deltas while the person is still
# talking (whisper-1 only returns text once the utterance ends). whisper-1 stays as
# the fallback for API keys/projects that don't have access to it.

def _openai_error_message(err: dict) -> str:
    """User-facing text for a Realtime error event."""
    code = (err.get("code") or "")
    msg = err.get("message", "Unknown OpenAI error")
    if code == "insufficient_quota" or "quota" in msg.lower():
        return "OUT_OF_CREDITS: Your OpenAI account is out of credits."
    return msg


def _transcription_session(model: str, source: str, role: str) -> dict:
    # No transcription "prompt": gpt-4o-mini-transcribe repeats it back as a
    # transcript when it hears silence or room noise.
    transcription = {"model": model}
    audio_input = {
        "format": {"type": "audio/pcm", "rate": 24000},
        "transcription": transcription,
        "turn_detection": {
            "type": "server_vad",
            # The mic hears keyboard, breathing and speaker bleed: ask for clearer speech
            "threshold": 0.6 if source == "mic" else 0.45,
            "prefix_padding_ms": 200,
            "silence_duration_ms": 350,
        },
    }
    if source == "mic":
        audio_input["noise_reduction"] = {"type": "near_field"}
    return {"type": "session.update", "session": {"type": "transcription", "audio": {"input": audio_input}}}


@router.websocket("/realtime")
async def realtime(ws: WebSocket):
    # WebSockets bypass CORS and HTTP middleware entirely - check Host + token here
    if ws.headers.get("host", "") not in ALLOWED_HOSTS or not _token_ok(ws.query_params.get("token")):
        await ws.close(code=1008)
        return
    await ws.accept()

    # "system" = the other side of the call (interviewer), "mic" = the user
    source = ws.query_params.get("source", "system")
    if source not in ("system", "mic"):
        source = "system"
    tag = f"[WS:{source}]"

    api_key = get_api_key()

    # GA Realtime transcription session. The Beta Realtime API was removed
    # ("Realtime Beta API no longer supported" / close 4000); GA drops the
    # OpenAI-Beta header and uses the ?intent=transcription endpoint.
    url = "wss://api.openai.com/v1/realtime?intent=transcription"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    if not api_key:
        print(f"{tag} ERROR: API key not found in profile or environment!")
        await ws.close(code=1008, reason="Missing API Key")
        return

    role = ""
    role = (_profile().get("target_role") or "").strip()

    print(f"{tag} Connecting to OpenAI at {url}...")
    try:
        async with websockets.connect(url, additional_headers=headers) as openai_ws:
            model = TRANSCRIBE_MODEL
            print(f"{tag} Connected to OpenAI Realtime API (model {model})")
            # GA transcription schema: audio config is nested under session.audio.input.
            # The client streams 24kHz mono PCM16; server VAD segments each utterance.
            await openai_ws.send(json.dumps(_transcription_session(model, source, role)))

            upstream_closed = {"code": None, "reason": ""}
            client_gone = False

            async def receive_from_client():
                nonlocal client_gone
                try:
                    while True:
                        message = await ws.receive()
                        if message.get("type") == "websocket.disconnect":
                            client_gone = True
                            break

                        if message.get("bytes") is not None:
                            import base64
                            _add_transcription_usage(len(message["bytes"]), model)
                            audio_b64 = base64.b64encode(message["bytes"]).decode()
                        else:
                            audio_b64 = message.get("text", "")

                        event = {
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64
                        }
                        await openai_ws.send(json.dumps(event))
                except WebSocketDisconnect:
                    client_gone = True
                except websockets.exceptions.ConnectionClosed:
                    pass  # upstream went away; receive_from_openai records why
                except Exception as e:
                    print(f"{tag} [receive_from_client] Error: {e}")
                finally:
                    # Client left: close upstream so receive_from_openai ends too
                    try:
                        await openai_ws.close()
                    except Exception:
                        pass

            async def receive_from_openai():
                nonlocal model
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        etype = event.get("type", "")
                        item_id = event.get("item_id", "")

                        if etype == "conversation.item.input_audio_transcription.delta":
                            delta = event.get("delta", "")
                            if delta:
                                await ws.send_json({"type": "transcript_delta", "item_id": item_id, "text": delta})

                        elif etype == "conversation.item.input_audio_transcription.completed":
                            transcript = event.get("transcript", "").strip()
                            print(f"{tag} [TRANSCRIPT] {transcript}")
                            await ws.send_json({"type": "transcript_final", "item_id": item_id, "text": transcript})

                        elif etype == "conversation.item.input_audio_transcription.failed":
                            print(f"{tag} [TRANSCRIPT FAILED] {event.get('error')}")
                            await ws.send_json({"type": "transcript_final", "item_id": item_id, "text": ""})

                        elif etype == "input_audio_buffer.speech_started":
                            await ws.send_json({"type": "speech_started", "item_id": item_id})

                        elif etype == "input_audio_buffer.speech_stopped":
                            await ws.send_json({"type": "speech_stopped", "item_id": item_id})

                        elif etype == "error":
                            err = event.get("error", {}) or {}
                            msg = _openai_error_message(err)
                            print(f"{tag} [OPENAI ERROR] {err.get('code')} - {err.get('message')}")
                            # No access to the streaming model: fall back to whisper-1
                            if model != FALLBACK_TRANSCRIBE_MODEL and (
                                "model" in (err.get("param") or "") or "model" in msg.lower()
                            ):
                                model = FALLBACK_TRANSCRIBE_MODEL
                                print(f"{tag} Falling back to {model}")
                                await openai_ws.send(json.dumps(_transcription_session(model, source, role)))
                                continue
                            await ws.send_json({"type": "error", "message": msg})

                    upstream_closed["code"] = openai_ws.close_code
                    upstream_closed["reason"] = openai_ws.close_reason or ""
                except websockets.exceptions.ConnectionClosed as e:
                    upstream_closed["code"], upstream_closed["reason"] = e.code, e.reason or ""
                except Exception as e:
                    upstream_closed["code"], upstream_closed["reason"] = -1, str(e)[:80]
                    print(f"{tag} [receive_from_openai] Exception: {e}")
                finally:
                    # Unblock receive_from_client's pending ws.receive() if the client is still there
                    if not client_gone:
                        upstream_closed["told_client"] = True
                        try:
                            await ws.close(code=4001, reason=f"upstream {upstream_closed['code']} {upstream_closed['reason']}"[:120])
                        except Exception:
                            pass

            await asyncio.gather(receive_from_client(), receive_from_openai())
            if upstream_closed.get("told_client"):
                print(f"{tag} OpenAI connection ended: {upstream_closed['code']} {upstream_closed['reason']} (client told to reconnect)")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"{tag} OpenAI Connection Closed: {e.code} {e.reason}")
        await ws.close(code=1011, reason=f"OpenAI Closed: {e.code}")
    except Exception as e:
        print(f"{tag} Connection error: {e}")
        # Try to send the error to the client before closing
        try:
            await ws.close(code=1011, reason=f"Upstream Error: {str(e)[:100]}")
        except:
            pass
