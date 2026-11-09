import base64
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.sync.server import ServerConnection, serve

from src.core.config import Settings, get_settings
from src.main import app
from src.transcribe.router import FLUSH_SILENCE, CloseCode

SPEECH = b"\x10\x00" * 2400


@dataclass
class FakeSpeaches:
    """Mimics the speaches realtime transcription events seen for one spoken phrase."""

    url: str = ""
    transcript: str = " Any recalls on a 2018 Honda Accord? "
    fail: bool = False
    paths: list[str] = field(default_factory=list)
    audio: list[bytes] = field(default_factory=list)

    def handle(self, conn: ServerConnection) -> None:
        assert conn.request is not None
        self.paths.append(conn.request.path)
        conn.send(json.dumps({"type": "session.created", "session": {}}))
        in_speech = False
        for raw in conn:
            audio = base64.b64decode(json.loads(raw)["audio"])
            self.audio.append(audio)
            if self.fail:
                conn.send(json.dumps({"type": "error", "error": {"message": "model missing"}}))
            elif any(audio) and not in_speech:
                in_speech = True
                conn.send(json.dumps({"type": "input_audio_buffer.speech_started"}))
            elif not any(audio) and in_speech:
                in_speech = False
                for event in (
                    {"type": "input_audio_buffer.speech_stopped"},
                    {"type": "input_audio_buffer.committed"},
                    {"type": "conversation.item.created"},
                    {
                        "type": "conversation.item.input_audio_transcription.completed",
                        "transcript": self.transcript,
                    },
                ):
                    conn.send(json.dumps(event))


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
