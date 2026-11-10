import { ShieldCheck } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useState } from "react";

import { BackendToggle } from "@/components/backend-toggle";
import { Chat } from "@/components/chat";
import { LandingPage } from "@/components/landing-page";
import { MascotHead } from "@/components/mascot-head";
import { ThemeToggle } from "@/components/theme-toggle";
import { VersionInfo } from "@/components/version-info";
import { useAgentBackend } from "@/hooks/use-agent-backend";
import { useApiStatus } from "@/hooks/use-api-status";
import { useChatConfig } from "@/hooks/use-chat-config";
import { useIdleTimeout } from "@/hooks/use-idle-timeout";
import { useTheme } from "@/hooks/use-theme";
import { IDLE_TIMEOUT_MS, THEME_TOGGLE_ENABLED } from "@/lib/config";

const NOD_MS = 550;

type Phase = "landing" | "nodding" | "entered";

function App() {
  const { status: apiStatus, health } = useApiStatus();
  const chatConfig = useChatConfig(apiStatus === "connected");
  const { backend, setBackend } = useAgentBackend(chatConfig);
  const { theme, setTheme } = useTheme();
  const reducedMotion = useReducedMotion() ?? false;
  const [phase, setPhase] = useState<Phase>("landing");
  const [landingSlot, setLandingSlot] = useState<HTMLDivElement | null>(null);
  const [siteSlot, setSiteSlot] = useState<HTMLDivElement | null>(null);
  const [chatBusy, setChatBusy] = useState(false);
  const entered = phase === "entered";

  const startEnter = useCallback(
    () => setPhase((current) => (current === "landing" ? "nodding" : current)),
    [],
  );
  const skip = useCallback(() => setPhase("entered"), []);

  // Let the head nod before handing off to the site.
  useEffect(() => {
    if (phase !== "nodding") return;
    const timer = window.setTimeout(skip, reducedMotion ? 0 : NOD_MS);
    return () => window.clearTimeout(timer);
  }, [phase, reducedMotion, skip]);

  // Bring the landing page back after inactivity, keeping the conversation.
  const returnToLanding = useCallback(() => setPhase("landing"), []);
  useIdleTimeout(entered && !chatBusy, IDLE_TIMEOUT_MS, returnToLanding);

  return (
    <>
      <AnimatePresence>
        {!entered && (
          <LandingPage
            key="landing"
            entering={phase === "nodding"}
            onEnter={startEnter}
            onSkip={skip}
            headSlotRef={setLandingSlot}
          />
        )}
      </AnimatePresence>
      <MascotHead
        landingSlot={landingSlot}
        siteSlot={siteSlot}
        docked={entered}
        nodding={phase === "nodding"}
        reducedMotion={reducedMotion}
      />
      <motion.div
        inert={!entered}
        initial={false}
        animate={
          entered || reducedMotion
            ? { opacity: 1, filter: "blur(0px)" }
            : { opacity: 0, filter: "blur(8px)" }
        }
        transition={{ duration: 0.9, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
        className="flex min-h-screen flex-col bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-50"
      >
        <header className="border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
          <div className="mx-auto flex min-h-16 max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-3 sm:py-0">
            <div className="flex items-center gap-3 font-semibold tracking-tight">
              <span className="grid size-9 place-items-center rounded-xl bg-teal-700 text-white">
                <ShieldCheck className="size-5" aria-hidden="true" />
              </span>
              Safety Assistant
            </div>
            <div className="flex items-center gap-4 whitespace-nowrap">
              {backend !== null && (
                <BackendToggle value={backend} onChange={setBackend} />
              )}
              <div
                className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400"
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
              {THEME_TOGGLE_ENABLED && (
                <ThemeToggle value={theme} onChange={setTheme} />
              )}
            </div>
          </div>
        </header>

        <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-5 py-12 sm:py-20">
          <section className="text-center">
            <div
              ref={setSiteSlot}
              aria-hidden="true"
              className="mx-auto mb-4 size-24"
            />
            <p className="mb-3 text-sm font-semibold tracking-wide text-teal-700 uppercase dark:text-teal-400">
              Product and vehicle safety
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              Make informed safety decisions.
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-base leading-7 text-pretty text-slate-600 sm:text-lg dark:text-slate-400">
              Research recalls, understand potential risks, and learn what steps
              to take next. Answers are grounded in official NHTSA and CPSC
              recall data.
            </p>
          </section>

          <Chat
            backend={backend}
            voiceInput={chatConfig?.voice_input === true}
            onBusyChange={setChatBusy}
          />

          <p className="mt-6 text-center text-xs leading-5 text-slate-600 dark:text-slate-400">
            Always confirm critical recall information with the manufacturer or
            responsible agency.
          </p>
        </main>

        <VersionInfo api={health} />
      </motion.div>
    </>
  );
}

export default App;
