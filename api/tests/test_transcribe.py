import base64
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.sync.server import ServerConnection, serve

from src.core.config import Settings, get_settings
from src.main import app
from src.transcribe import router as transcribe_router
from src.transcribe.router import AUDIO_BURST_SECONDS, FLUSH_SILENCE, MAX_CHUNK_BYTES, CloseCode

SPEECH = b"\x10\x00" * 2400


@dataclass
class FakeSpeaches:
    """Mimics speaches realtime transcription, including its event order.

    Like speaches, it handles client events in order, sends speech_stopped before replying to
    a later session.update, and sends committed and the transcript after that.
    """

    url: str = ""
    transcript: str = " Any recalls on a 2018 Honda Accord? "
    fail: bool = False
    # Simulates a slow server: every client event is handled this much later.
    event_delay: float = 0.0
    # Delay between speech_stopped and the committed/transcript events; None never sends them.
    transcript_delay: float | None = 0.0
    paths: list[str] = field(default_factory=list)
    audio: list[bytes] = field(default_factory=list)

    def transcribe(self, conn: ServerConnection) -> None:
        for event in (
            {"type": "input_audio_buffer.committed"},
            {"type": "conversation.item.created"},
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": self.transcript,
            },
        ):
            conn.send(json.dumps(event))

    def handle(self, conn: ServerConnection) -> None:
        assert conn.request is not None
        self.paths.append(conn.request.path)
        conn.send(json.dumps({"type": "session.created", "session": {}}))
        in_speech = False
        for raw in conn:
            time.sleep(self.event_delay)
            message = json.loads(raw)
            if message["type"] == "session.update":
                conn.send(json.dumps({"type": "session.updated", "session": {}}))
                continue
            audio = base64.b64decode(message["audio"])
            self.audio.append(audio)
            if self.fail:
                conn.send(json.dumps({"type": "error", "error": {"message": "model missing"}}))
            elif any(audio) and not in_speech:
                in_speech = True
                conn.send(json.dumps({"type": "input_audio_buffer.speech_started"}))
            elif not any(audio) and in_speech:
                in_speech = False
                conn.send(json.dumps({"type": "input_audio_buffer.speech_stopped"}))
                if self.transcript_delay is not None:
                    threading.Timer(self.transcript_delay, self.transcribe, [conn]).start()


@pytest.fixture
def speaches() -> Iterator[FakeSpeaches]:
    fake = FakeSpeaches()
    with serve(fake.handle, "127.0.0.1", 0) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        fake.url = f"http://127.0.0.1:{server.socket.getsockname()[1]}"
        yield fake
        server.shutdown()


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def use_settings(**values: object) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **values)


def close_code(ws: object) -> int:
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()  # type: ignore[attr-defined]
    return closed.value.code


def test_transcribe_relays_audio_and_returns_phrases(speaches: FakeSpeaches) -> None:
    use_settings(stt_url=speaches.url)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(SPEECH)
        assert ws.receive_json() == {"type": "speech_started"}
        ws.send_json({"type": "stop"})
        assert ws.receive_json() == {
            "type": "transcript",
            "text": "Any recalls on a 2018 Honda Accord?",
        }
        assert close_code(ws) == 1000

    query = parse_qs(urlsplit(speaches.paths[0]).query)
    assert urlsplit(speaches.paths[0]).path == "/v1/realtime"
    assert query == {
        "model": ["Systran/faster-distil-whisper-small.en"],
        "intent": ["transcription"],
        "language": ["en"],
    }
    # Stopping appends silence so speaches finishes the phrase in progress.
    assert speaches.audio == [SPEECH, FLUSH_SILENCE]
    assert app.state.stt_sessions == 0


def stop_and_collect(ws: object) -> list[str]:
    """Sends stop and returns the transcripts received before the session closes normally."""
    ws.send_json({"type": "stop"})  # type: ignore[attr-defined]
    texts = []
    while True:
        try:
            message = ws.receive_json()  # type: ignore[attr-defined]
        except WebSocketDisconnect as closed:
            assert closed.code == 1000
            return texts
        if message["type"] == "transcript":
            texts.append(message["text"])


def test_transcribe_waits_for_delayed_speech_events(speaches: FakeSpeaches) -> None:
    # The stop arrives before speaches has reported any speech.
    speaches.event_delay = 0.5
    use_settings(stt_url=speaches.url)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(SPEECH)
        assert stop_and_collect(ws) == ["Any recalls on a 2018 Honda Accord?"]


def test_transcribe_waits_for_transcript_after_speech_stops(speaches: FakeSpeaches) -> None:
    # speaches acknowledges the flush before committing and transcribing the last phrase.
    speaches.transcript_delay = 1.5
    use_settings(stt_url=speaches.url)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(SPEECH)
        assert ws.receive_json() == {"type": "speech_started"}
        assert stop_and_collect(ws) == ["Any recalls on a 2018 Honda Accord?"]


def test_transcribe_fails_when_last_transcript_never_arrives(
    speaches: FakeSpeaches, monkeypatch: pytest.MonkeyPatch
) -> None:
    speaches.transcript_delay = None
    monkeypatch.setattr(transcribe_router, "FLUSH_TIMEOUT_SECONDS", 0.5)
    use_settings(stt_url=speaches.url)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(SPEECH)
        assert ws.receive_json() == {"type": "speech_started"}
        ws.send_json({"type": "stop"})
        assert close_code(ws) == CloseCode.FAILED


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({}, CloseCode.NOT_CONFIGURED),
        ({"stt_url": "http://stt:8000", "stt_max_sessions": 0}, CloseCode.BUSY),
        ({"stt_url": "http://127.0.0.1:1"}, CloseCode.FAILED),
    ],
)
def test_transcribe_rejects_unavailable_sessions(
    settings: dict[str, object], expected: int
) -> None:
    use_settings(**settings)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert close_code(ws) == expected


def test_transcribe_rejects_invalid_audio(speaches: FakeSpeaches) -> None:
    use_settings(stt_url=speaches.url)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"\x01\x02\x03")
        assert close_code(ws) == CloseCode.INVALID_AUDIO


def test_transcribe_rejects_audio_faster_than_real_time(speaches: FakeSpeaches) -> None:
    use_settings(stt_url=speaches.url)
    burst_chunks = int(AUDIO_BURST_SECONDS)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        for _ in range(burst_chunks + 1):
            ws.send_bytes(bytes(MAX_CHUNK_BYTES))
        assert close_code(ws) == CloseCode.INVALID_AUDIO

    # The startup burst is forwarded; the chunk beyond it is not.
    assert len(speaches.audio) == burst_chunks


def test_transcribe_enforces_session_audio_budget(speaches: FakeSpeaches) -> None:
    use_settings(stt_url=speaches.url, stt_max_session_seconds=1.5)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(bytes(MAX_CHUNK_BYTES))
        ws.send_bytes(bytes(MAX_CHUNK_BYTES))
        assert close_code(ws) == CloseCode.TIME_LIMIT

    assert len(speaches.audio) == 1


def test_transcribe_reports_server_errors(speaches: FakeSpeaches) -> None:
    speaches.fail = True
    use_settings(stt_url=speaches.url)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(SPEECH)
        assert close_code(ws) == CloseCode.FAILED


def test_transcribe_enforces_session_time_limit(speaches: FakeSpeaches) -> None:
    use_settings(stt_url=speaches.url, stt_max_session_seconds=0.5)

    with TestClient(app).websocket_connect("/api/transcribe") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(SPEECH)
        assert ws.receive_json() == {"type": "speech_started"}
        assert close_code(ws) == CloseCode.TIME_LIMIT
