import { ArrowUp, ExternalLink, LoaderCircle } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { Button } from "@/components/ui/button";
import {
  ChatError,
  sendChat,
  type ChatMessage,
  type ChatSource,
} from "@/lib/api";

const MAX_MESSAGE_LENGTH = 4000;
// Keep the request under the API's 20-message limit while preserving recent context.
const MAX_HISTORY_MESSAGES = 19;

interface ChatTurn extends ChatMessage {
  sources?: ChatSource[];
}

function errorMessage(error: unknown): string {
  if (error instanceof ChatError && error.status === 503) {
    return "The research assistant isn't configured yet. Please try again later.";
  }
  return "Something went wrong while researching your question. Please try again.";
}

export function Chat() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [turns, isSending]);

  async function submit() {
    const content = draft.trim();
    if (!content || isSending) return;

    const nextTurns: ChatTurn[] = [...turns, { role: "user", content }];
    setTurns(nextTurns);
    setDraft("");
    setError(null);
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
        controller.signal,
      );
      setTurns([
        ...nextTurns,
        {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
        },
      ]);
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "AbortError")
        return;
      setTurns(turns);
      setDraft(content);
      setError(errorMessage(caught));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsSending(false);
      }
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void submit();
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
                  : "mr-auto max-w-[95%] rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 whitespace-pre-wrap text-slate-800 shadow-sm"
              }
            >
              <span className="sr-only">
                {turn.role === "user" ? "You:" : "Assistant:"}
              </span>
              {turn.content}
              {turn.sources && turn.sources.length > 0 && (
                <div className="mt-3 border-t border-slate-100 pt-3 whitespace-normal">
                  <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                    Sources
                  </p>
                  <ul className="flex flex-col gap-1.5">
                    {turn.sources.map((source) => (
                      <li key={source.id}>
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-start gap-1.5 text-xs text-teal-800 underline-offset-2 hover:underline"
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
            </li>
          ))}
          {isSending && (
            <li className="mr-auto flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
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
        <p
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800"
        >
          {error}
        </p>
      )}

      <form
        onSubmit={onSubmit}
        className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4"
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
          className="w-full resize-none bg-transparent px-2 py-2 text-sm text-slate-700 outline-none placeholder:text-slate-400"
        />
        <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
          <span className="px-2 text-xs text-slate-600">
            Answers use live NHTSA and CPSC recall data
          </span>
          <Button
            type="submit"
            size="icon"
            disabled={isSending || !draft.trim()}
            aria-label="Send question"
          >
            <ArrowUp className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </form>
    </section>
  );
}
