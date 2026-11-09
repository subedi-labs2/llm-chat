"""Voice input: relays browser microphone audio to a speaches realtime transcription session.

Browser protocol on ``/api/transcribe``:

- Client sends binary frames of 16-bit little-endian mono PCM at 24 kHz, then ``{"type": "stop"}``.
- Server sends ``{"type": "ready"}`` once audio can be streamed, ``{"type": "speech_started"}``,
  and ``{"type": "transcript", "text": "..."}`` after each spoken phrase.
- After a stop, the server closes with 1000 once the last phrase is transcribed. Errors close
  with one of the ``CloseCode`` values.
"""

import asyncio
import base64
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transcribe"])

SAMPLE_RATE = 24_000
BYTES_PER_SECOND = SAMPLE_RATE * 2
MAX_CHUNK_BYTES = BYTES_PER_SECOND
# speaches ends a phrase only once its latest 3 s of audio are silent, so stopping sends 3.5 s.
FLUSH_SILENCE = bytes(BYTES_PER_SECOND * 7 // 2)
# After a stop, how long to wait for speaches to react to the silence before finishing.
SETTLE_SECONDS = 0.75
FLUSH_TIMEOUT_SECONDS = 30.0
POLL_SECONDS = 0.25


class CloseCode(IntEnum):
    INVALID_AUDIO = 4400
    TIME_LIMIT = 4408
    BUSY = 4429
    FAILED = 4502
    NOT_CONFIGURED = 4503


class UpstreamError(Exception):
    """The transcription server failed or ended the session."""


class ClientGone(Exception):
    """The browser disconnected."""


class InvalidAudio(Exception):
    """The browser sent audio in an unexpected format."""


@dataclass
class SessionState:
    in_speech: bool = False
    # Phrases sent for transcription whose transcript hasn't arrived yet.
    pending: int = 0
    stopped_at: float | None = None

    def finished(self) -> bool:
        if self.stopped_at is None or self.in_speech or self.pending:
            return False
        return time.monotonic() - self.stopped_at >= SETTLE_SECONDS


def upstream_url(settings: Settings) -> str:
    assert settings.stt_url
    parts = urlsplit(settings.stt_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    query = {"model": settings.stt_model, "intent": "transcription"}
    if settings.stt_language:
        query["language"] = settings.stt_language
    path = parts.path.rstrip("/") + "/v1/realtime"
    return urlunsplit((scheme, parts.netloc, path, urlencode(query), ""))


def append_event(audio: bytes) -> str:
    return json.dumps(
        {"type": "input_audio_buffer.append", "audio": base64.b64encode(audio).decode()}
    )


def is_stop(text: str) -> bool:
    try:
        message = json.loads(text)
    except ValueError:
        return False
    return isinstance(message, dict) and message.get("type") == "stop"


async def forward_audio(ws: WebSocket, upstream: ClientConnection, state: SessionState) -> None:
    """Streams browser audio to speaches until the browser asks to stop."""
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            raise ClientGone
        if (audio := message.get("bytes")) is not None:
            if not audio or len(audio) > MAX_CHUNK_BYTES or len(audio) % 2:
                raise InvalidAudio
            await upstream.send(append_event(audio))
        elif is_stop(message.get("text") or ""):
            await upstream.send(append_event(FLUSH_SILENCE))
            state.stopped_at = time.monotonic()
            return


async def forward_events(ws: WebSocket, upstream: ClientConnection, state: SessionState) -> None:
    """Sends speaches results to the browser until the session finishes after a stop."""
    while not state.finished():
        try:
            async with asyncio.timeout(POLL_SECONDS):
                raw = await upstream.recv()
        except TimeoutError:
            continue
        event: dict[str, Any] = json.loads(raw)
        match event.get("type"):
            case "input_audio_buffer.speech_started":
                state.in_speech = True
                await ws.send_json({"type": "speech_started"})
            case "input_audio_buffer.speech_stopped":
                state.in_speech = False
            case "input_audio_buffer.committed":
                state.pending += 1
            case "conversation.item.input_audio_transcription.completed":
                state.pending = max(state.pending - 1, 0)
                if text := str(event.get("transcript") or "").strip():
                    await ws.send_json({"type": "transcript", "text": text})
            case "error":
                logger.error("Transcription server error: %s", event.get("error"))
                raise UpstreamError


async def relay(ws: WebSocket, settings: Settings) -> None:
    async with connect(upstream_url(settings), open_timeout=10, max_size=2**20) as upstream:
        created = json.loads(await asyncio.wait_for(upstream.recv(), timeout=10))
        if created.get("type") != "session.created":
            raise UpstreamError
        await ws.send_json({"type": "ready"})

        state = SessionState()
        audio = asyncio.create_task(forward_audio(ws, upstream, state))
        events = asyncio.create_task(forward_events(ws, upstream, state))
        try:
            await asyncio.wait({audio, events}, return_when=asyncio.FIRST_COMPLETED)
            if not audio.done():
                # Events only end on their own after a stop, so this is an upstream failure.
                events.result()
                raise UpstreamError
            audio.result()
            async with asyncio.timeout(FLUSH_TIMEOUT_SECONDS):
                await events
        finally:
            audio.cancel()
            events.cancel()
            await asyncio.gather(audio, events, return_exceptions=True)


async def close(ws: WebSocket, code: int = 1000, reason: str = "") -> None:
    # The browser may already be gone.
    with contextlib.suppress(RuntimeError, OSError, WebSocketDisconnect):
        await ws.close(code, reason)


@router.websocket("/transcribe")
async def transcribe(ws: WebSocket, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    # Accept before rejecting so the browser receives the close code.
    await ws.accept()
    if not settings.stt_url:
        await close(ws, CloseCode.NOT_CONFIGURED, "Voice input is not configured")
        return

    active: int = getattr(ws.app.state, "stt_sessions", 0)
    if active >= settings.stt_max_sessions:
        await close(ws, CloseCode.BUSY, "Voice input is busy")
        return
    ws.app.state.stt_sessions = active + 1
    limit = asyncio.timeout(settings.stt_max_session_seconds)
    try:
        async with limit:
            await relay(ws, settings)
        await close(ws)
    except (ClientGone, WebSocketDisconnect):
        pass
    except InvalidAudio:
        await close(ws, CloseCode.INVALID_AUDIO, "Invalid audio")
    except TimeoutError:
        if limit.expired():
            await close(ws, CloseCode.TIME_LIMIT, "Voice input time limit reached")
        else:
            logger.exception("Transcription server timed out")
            await close(ws, CloseCode.FAILED, "Transcription failed")
    except (UpstreamError, WebSocketException, OSError, ValueError):
        logger.exception("Transcription session failed")
        await close(ws, CloseCode.FAILED, "Transcription failed")
    finally:
        ws.app.state.stt_sessions -= 1
