/** Live voice input over the /api/transcribe WebSocket (protocol in api/src/transcribe/router.py). */

export type VoiceInputError =
  "permission" | "unavailable" | "busy" | "time_limit" | "failed";

const CLOSE_ERRORS: Record<number, VoiceInputError> = {
  4408: "time_limit",
  4429: "busy",
  4503: "unavailable",
};

const STOP_MESSAGE = JSON.stringify({ type: "stop" });
// Audio captured before the server is ready (100 ms chunks).
const MAX_QUEUED_CHUNKS = 50;

interface ServerMessage {
  type: "ready" | "speech_started" | "transcript";
  text?: string;
}

export interface VoiceInputHandlers {
  /** Called with each transcribed phrase. */
  onTranscript: (text: string) => void;
  /** Called once when the session ends; `error` is null after a normal stop. */
  onEnd: (error: VoiceInputError | null) => void;
}

export interface VoiceInputSession {
  /** Stops recording. Phrases still being transcribed arrive before `onEnd`. */
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

/** Starts recording; call from a user gesture so the browser allows audio capture. */
export function startVoiceInput({
  onTranscript,
  onEnd,
}: VoiceInputHandlers): VoiceInputSession {
  const context = new AudioContext();
  const socket = new WebSocket(transcribeUrl());
  socket.binaryType = "arraybuffer";
  const queue: ArrayBuffer[] = [];
  let stream: MediaStream | null = null;
  let recorder: AudioWorkletNode | null = null;
  let recording = true;
  let ready = false;
  let ended = false;

  function stopAudio() {
    recording = false;
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

  function sendAudio(chunk: ArrayBuffer) {
    if (ready) socket.send(chunk);
    else if (queue.length < MAX_QUEUED_CHUNKS) queue.push(chunk);
  }

  socket.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
    if (typeof event.data !== "string") return;
    const message = JSON.parse(event.data) as ServerMessage;
    if (message.type === "ready") {
      ready = true;
      queue.splice(0).forEach((chunk) => socket.send(chunk));
      if (!recording) socket.send(STOP_MESSAGE);
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
    if (!recording) return stopAudio();
    await context.audioWorklet.addModule("/pcm-recorder-worklet.js");
    if (!recording) return stopAudio();
    recorder = new AudioWorkletNode(context, "pcm-recorder");
    recorder.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      sendAudio(event.data);
    };
    // The recorder outputs silence; connecting it keeps it processing in every browser.
    context.createMediaStreamSource(stream).connect(recorder);
    recorder.connect(context.destination);
    await context.resume();
  }

  startAudio().catch(() => {
    if (recording) finish("failed");
  });

  return {
    stop() {
      if (ended || !recording) return;
      stopAudio();
      // Before the server is ready, the stop is sent once it is.
      if (ready) socket.send(STOP_MESSAGE);
    },
    cancel() {
      finish(null, false);
    },
  };
}
