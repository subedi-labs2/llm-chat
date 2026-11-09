import { useEffect, useRef, useState } from "react";

import {
  startVoiceInput,
  type VoiceInputError,
  type VoiceInputSession,
} from "@/lib/transcribe";

/** `finishing` means recording stopped and the last phrases are being transcribed. */
export type VoiceInputStatus = "idle" | "recording" | "finishing";

export interface VoiceInput {
  status: VoiceInputStatus;
  error: VoiceInputError | null;
  start: () => void;
  stop: () => void;
}

export function useVoiceInput(
  onTranscript: (text: string) => void,
): VoiceInput {
  const [status, setStatus] = useState<VoiceInputStatus>("idle");
  const [error, setError] = useState<VoiceInputError | null>(null);
  const sessionRef = useRef<VoiceInputSession | null>(null);
  const onTranscriptRef = useRef(onTranscript);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  });

  useEffect(() => () => sessionRef.current?.cancel(), []);

  function start() {
    if (sessionRef.current) return;
    setError(null);
    setStatus("recording");
    sessionRef.current = startVoiceInput({
      onTranscript: (text) => onTranscriptRef.current(text),
      onEnd: (endError) => {
        sessionRef.current = null;
        setStatus("idle");
        setError(endError);
      },
    });
  }

  function stop() {
    if (!sessionRef.current) return;
    sessionRef.current.stop();
    setStatus("finishing");
  }

  return { status, error, start, stop };
}
