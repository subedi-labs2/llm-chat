import {
  ArrowUp,
  ExternalLink,
  LoaderCircle,
  Mic,
  RotateCcw,
  Square,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { useVoiceInput } from "@/hooks/use-voice-input";
import {
  AGENT_BACKEND_LABELS,
  ChatError,
  sendChat,
  type AgentBackend,
  type ChatMessage,
  type ChatSource,
} from "@/lib/api";
import { isVoiceInputSupported, type VoiceInputError } from "@/lib/transcribe";

const MAX_MESSAGE_LENGTH = 4000;
// Keep the request under the API's 20-message limit while preserving recent context.
const MAX_HISTORY_MESSAGES = 19;

interface ChatTurn extends ChatMessage {
  sources?: ChatSource[];
  backend?: AgentBackend;
}

interface ChatProps {
  /** The agent backend to request, or null to use the API's default. */
  backend: AgentBackend | null;
  /** Show the microphone button (the API has voice input configured). */
  voiceInput: boolean;
}

const VOICE_INPUT_ERRORS: Record<VoiceInputError, string> = {
  permission:
    "Microphone access is blocked. Allow it in your browser to use voice input.",
  unavailable: "Voice input isn't available right now.",
  busy: "Voice input is busy. Please try again in a moment.",
  time_limit:
    "Voice input reached its time limit. Your words so far were kept.",
  failed: "Voice input stopped unexpectedly. Please try again.",
};

function appendTranscript(draft: string, text: string): string {
  const joined = draft.trim() ? `${draft.trimEnd()} ${text}` : text;
  return joined.slice(0, MAX_MESSAGE_LENGTH);
}

function errorMessage(error: unknown): string {
  if (error instanceof ChatError && error.status === 503) {
    return "The research assistant isn't configured yet. Please try again later.";
  }
  return "Something went wrong while researching your question. Please try again.";
}

export function Chat({ backend, voiceInput }: ChatProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const voice = useVoiceInput((text) =>
    setDraft((current) => appendTranscript(current, text)),
  );
  const showVoiceInput = voiceInput && isVoiceInputSupported();
  const isListening = voice.status !== "idle";

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [turns, isSending]);

  // A failed question stays as the last turn until it is retried or replaced.
  const answeredTurns = failedQuestion === null ? turns : turns.slice(0, -1);

  async function send(content: string) {
    const nextTurns: ChatTurn[] = [...answeredTurns, { role: "user", content }];
    setTurns(nextTurns);
    setError(null);
    setFailedQuestion(null);
    setIsSending(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const history = nextTurns
        .slice(-MAX_HISTORY_MESSAGES)
        .map(({ role, content: text }) => ({ role, content: text }));
      const firstUser = history.findIndex((turn) => turn.role === "user");
      const response = await sendChat(
        history.slice(firstUser),
        backend,
        controller.signal,
      );
      setTurns([
        ...nextTurns,
        {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          backend: response.backend,
        },
      ]);
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "AbortError")
        return;
      setFailedQuestion(content);
      setError(errorMessage(caught));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsSending(false);
      }
    }
  }

  function submit() {
    const content = draft.trim();
    if (!content || isSending || isListening) return;
    setDraft("");
    void send(content);
  }

  function retry() {
    if (failedQuestion === null || isSending) return;
    void send(failedQuestion);
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <section className="mt-10 flex flex-col gap-4">
      {turns.length > 0 && (
        <ol
          className="flex flex-col gap-4"
          aria-live="polite"
          aria-label="Conversation"
        >
          {turns.map((turn, index) => (
            <li
              key={index}
              className={
                turn.role === "user"
                  ? "ml-auto max-w-[85%] rounded-2xl bg-teal-700 px-4 py-3 text-sm whitespace-pre-wrap text-white"
                  : "mr-auto max-w-[95%] rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 whitespace-pre-wrap text-slate-800 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
              }
            >
              <span className="sr-only">
                {turn.role === "user" ? "You:" : "Assistant:"}
              </span>
              {turn.content}
              {turn.sources && turn.sources.length > 0 && (
                <div className="mt-3 border-t border-slate-100 pt-3 whitespace-normal dark:border-slate-800">
                  <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-slate-400">
                    Sources
                  </p>
                  <ul className="flex flex-col gap-1.5">
                    {turn.sources.map((source) => (
                      <li key={source.id}>
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-start gap-1.5 text-xs text-teal-800 underline-offset-2 hover:underline dark:text-teal-300"
                        >
                          <ExternalLink
                            className="mt-0.5 size-3 shrink-0"
                            aria-hidden="true"
                          />
                          <span>
                            {source.agency} {source.id}: {source.title}
                          </span>
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {backend !== null && turn.backend && (
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                  Answered with {AGENT_BACKEND_LABELS[turn.backend]}
                </p>
              )}
            </li>
          ))}
          {isSending && (
            <li className="mr-auto flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
              <LoaderCircle
                className="size-4 animate-spin"
                aria-hidden="true"
              />
              Checking official recall sources…
            </li>
          )}
        </ol>
      )}
      <div ref={endRef} />

      {error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
        >
          <p>{error}</p>
          {failedQuestion !== null && (
            <Button
              type="button"
              variant="outline"
              onClick={retry}
              disabled={isSending}
              className="h-8 shrink-0 px-3"
            >
              <RotateCcw className="size-4" aria-hidden="true" />
              Retry
            </Button>
          )}
        </div>
      )}

      <form
        onSubmit={onSubmit}
        className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4 dark:border-slate-800 dark:bg-slate-900"
      >
        <label htmlFor="safety-question" className="sr-only">
          Ask a product safety question
        </label>
        <textarea
          id="safety-question"
          rows={3}
          value={draft}
          maxLength={MAX_MESSAGE_LENGTH}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a product or vehicle recall, e.g. “Any recalls on a 2018 Honda Accord?”"
          className="w-full resize-none bg-transparent px-2 py-2 text-sm text-slate-700 outline-none placeholder:text-slate-400 dark:text-slate-200 dark:placeholder:text-slate-500"
        />
        <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3 dark:border-slate-800">
          <span
            className={`px-2 text-xs ${
              voice.error && !isListening
                ? "text-rose-700 dark:text-rose-300"
                : "text-slate-600 dark:text-slate-400"
            }`}
            aria-live="polite"
          >
            {voice.status === "connecting"
              ? "Starting voice input… wait for “Listening” to speak"
              : voice.status === "recording"
                ? "Listening… your words appear after each pause"
                : voice.status === "finishing"
                  ? "Finishing transcription…"
                  : voice.error
                    ? VOICE_INPUT_ERRORS[voice.error]
                    : "Answers use live NHTSA and CPSC recall data"}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            {showVoiceInput && (
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={voice.status === "idle" ? voice.start : voice.stop}
                disabled={voice.status === "finishing"}
                aria-pressed={voice.status === "recording"}
                aria-label={
                  voice.status === "connecting"
                    ? "Cancel voice input"
                    : voice.status === "recording"
                      ? "Stop voice input"
                      : "Start voice input"
                }
              >
                {voice.status === "recording" ? (
                  <Square
                    className="size-4 animate-pulse fill-rose-600 text-rose-600"
                    aria-hidden="true"
                  />
                ) : voice.status !== "idle" ? (
                  <LoaderCircle
                    className="size-4 animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Mic className="size-4" aria-hidden="true" />
                )}
              </Button>
            )}
            <Button
              type="submit"
              size="icon"
              disabled={isSending || isListening || !draft.trim()}
              aria-label="Send question"
            >
              <ArrowUp className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </form>
    </section>
  );
}
