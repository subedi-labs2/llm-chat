import { ArrowUp, CheckCircle2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getHealth } from "@/lib/api";

type ApiStatus = "checking" | "connected" | "unavailable";

function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(() => setApiStatus("connected"))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setApiStatus("unavailable");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-950">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-5">
          <div className="flex items-center gap-3 font-semibold tracking-tight">
            <span className="grid size-9 place-items-center rounded-xl bg-teal-700 text-white">
              <ShieldCheck className="size-5" aria-hidden="true" />
            </span>
            Safety Assistant
          </div>
          <div
            className="flex items-center gap-2 text-xs font-medium text-slate-500"
            aria-live="polite"
          >
            <span
              className={`size-2 rounded-full ${
                apiStatus === "connected"
                  ? "bg-emerald-500"
                  : apiStatus === "unavailable"
                    ? "bg-rose-500"
                    : "animate-pulse bg-amber-400"
              }`}
            />
            API {apiStatus}
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-5 py-12 sm:py-20">
        <section className="text-center">
          <div className="mx-auto mb-6 grid size-14 place-items-center rounded-2xl border border-teal-100 bg-teal-50 text-teal-700">
            <CheckCircle2 className="size-7" aria-hidden="true" />
          </div>
          <p className="mb-3 text-sm font-semibold tracking-wide text-teal-700 uppercase">
            Product and vehicle safety
          </p>
          <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
            Make informed safety decisions.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-pretty text-base leading-7 text-slate-600 sm:text-lg">
            Research recalls, understand potential risks, and learn what steps to take next. Safety
            information and guided research are coming soon.
          </p>
        </section>

        <section className="mt-10 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4">
          <label htmlFor="safety-question" className="sr-only">
            Ask a product safety question
          </label>
          <textarea
            id="safety-question"
            rows={3}
            disabled
            placeholder="Ask about a product or vehicle recall…"
            className="w-full resize-none bg-transparent px-2 py-2 text-sm text-slate-700 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
          />
          <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <span className="px-2 text-xs text-slate-400">Research chat coming soon</span>
            <Button size="icon" disabled aria-label="Send question">
              <ArrowUp className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </section>

        <p className="mt-6 text-center text-xs leading-5 text-slate-400">
          Always confirm critical recall information with the manufacturer or responsible agency.
        </p>
      </main>
    </div>
  );
}

export default App;
