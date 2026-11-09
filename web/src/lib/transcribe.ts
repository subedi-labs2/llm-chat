/** Live voice input over the /api/transcribe WebSocket (protocol in api/src/transcribe/router.py). */

export type VoiceInputError =
  "permission" | "unavailable" | "busy" | "time_limit" | "failed";

const CLOSE_ERRORS: Record<number, VoiceInputError> = {
  4408: "time_limit",
  4429: "busy",
  4503: "unavailable",
};

const STOP_MESSAGE = JSON.stringify({ type: "stop" });
// Fallback if the recorder never confirms the flush (for example, a suspended AudioContext).
const FLUSH_TIMEOUT_MS = 500;

interface ServerMessage {
  type: "ready" | "speech_started" | "transcript";
  text?: string;
}

export interface VoiceInputHandlers {
  /** Called once the server is ready and audio is being captured; speech before this is not heard. */
  onRecording: () => void;
  /** Called with each transcribed phrase. */
  onTranscript: (text: string) => void;
  /** Called once when the session ends; `error` is null after a normal stop. */
  onEnd: (error: VoiceInputError | null) => void;
}

export interface VoiceInputSession {
  /**
   * Stops recording. Phrases still being transcribed arrive before `onEnd`. Before
   * `onRecording`, nothing has been captured, so the session ends right away.
   */
  stop: () => void;
  /** Ends the session immediately without calling `onEnd`. */
  cancel: () => void;
}

export function isVoiceInputSupported(): boolean {
  return (
    typeof window.AudioWorkletNode === "function" &&
    typeof navigator.mediaDevices?.getUserMedia === "function"
  );
}

function transcribeUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/transcribe`;
}

/**
 * Connects and prepares the microphone, then records once the server is ready, so no
 * speech is buffered or dropped while connecting. Call from a user gesture so the
 * browser allows audio capture.
 */
export function startVoiceInput({
  onRecording,
  onTranscript,
  onEnd,
}: VoiceInputHandlers): VoiceInputSession {
  const context = new AudioContext();
  const socket = new WebSocket(transcribeUrl());
  socket.binaryType = "arraybuffer";
  let stream: MediaStream | null = null;
  let recorder: AudioWorkletNode | null = null;
  let phase: "connecting" | "recording" | "flushing" | "stopped" = "connecting";
  let ready = false;
  let ended = false;

  function stopAudio() {
    phase = "stopped";
    recorder?.port.close();
    recorder?.disconnect();
    stream?.getTracks().forEach((track) => track.stop());
    if (context.state !== "closed") void context.close().catch(() => {});
  }

  function finish(error: VoiceInputError | null, notify = true) {
    if (ended) return;
    ended = true;
    stopAudio();
    socket.close();
    if (notify) onEnd(error);
  }

  /** Starts capturing once both the server and the microphone are ready. */
  function startRecording() {
    if (!ready || !stream || !recorder || phase !== "connecting") return;
    phase = "recording";
    // The recorder outputs silence; connecting it keeps it processing in every browser.
    context.createMediaStreamSource(stream).connect(recorder);
    recorder.connect(context.destination);
    context.resume().then(onRecording, () => finish("failed"));
  }

  socket.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
    if (typeof event.data !== "string") return;
    const message = JSON.parse(event.data) as ServerMessage;
    if (message.type === "ready") {
      ready = true;
      startRecording();
    } else if (message.type === "transcript" && message.text) {
      onTranscript(message.text);
    }
  };
  socket.onclose = (event) => {
    finish(event.code === 1000 ? null : (CLOSE_ERRORS[event.code] ?? "failed"));
  };

  async function startAudio() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
    } catch {
      finish("permission");
      return;
    }
    if (phase !== "connecting") return stopAudio();
    await context.audioWorklet.addModule("/pcm-recorder-worklet.js");
    if (phase !== "connecting") return stopAudio();
    recorder = new AudioWorkletNode(context, "pcm-recorder");
    recorder.port.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
      if (event.data === "flushed") endRecording();
      else if (!ended) socket.send(event.data);
    };
    startRecording();
  }

  /** Sends stop after the recorder's last audio, then releases the microphone. */
  function endRecording() {
    if (phase !== "flushing") return;
    stopAudio();
    if (!ended) socket.send(STOP_MESSAGE);
  }

  startAudio().catch(() => {
    if (phase === "connecting") finish("failed");
  });

  return {
    stop() {
      if (ended) return;
      if (phase === "connecting") return finish(null);
      if (phase !== "recording") return;
      // The recorder posts only full 100 ms chunks; flush the partial one so the last
      // syllable isn't lost. Port messages arrive in order, so its audio precedes "flushed".
      phase = "flushing";
      recorder?.port.postMessage("flush");
      setTimeout(endRecording, FLUSH_TIMEOUT_MS);
    },
    cancel() {
      finish(null, false);
    },
  };
}
