import { CheckCircle2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { Chat } from "@/components/chat";
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
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Make informed safety decisions.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-base leading-7 text-pretty text-slate-600 sm:text-lg">
            Research recalls, understand potential risks, and learn what steps
            to take next. Answers are grounded in official NHTSA and CPSC recall
            data.
          </p>
        </section>

        <Chat />

        <p className="mt-6 text-center text-xs leading-5 text-slate-600">
          Always confirm critical recall information with the manufacturer or
          responsible agency.
        </p>
      </main>
    </div>
  );
}

export default App;
