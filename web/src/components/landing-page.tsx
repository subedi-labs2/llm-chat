import { ArrowRight } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";

const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];

type LandingPageProps = {
  entering: boolean;
  onEnter: () => void;
  onSkip: () => void;
  headSlotRef: (element: HTMLDivElement | null) => void;
};

export function LandingPage({
  entering,
  onEnter,
  onSkip,
  headSlotRef,
}: LandingPageProps) {
  const reducedMotion = useReducedMotion() ?? false;
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    buttonRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onSkip();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onSkip]);

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-labelledby="landing-title"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden bg-slate-950 text-slate-50"
      exit={
        reducedMotion
          ? { opacity: 0, transition: { duration: 0.2 } }
          : {
              opacity: 0,
              scale: 1.12,
              filter: "blur(16px)",
              transition: { duration: 0.8, ease: [0.65, 0, 0.35, 1] },
            }
      }
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_38%,rgba(45,212,191,0.22),transparent_55%),radial-gradient(circle_at_80%_90%,rgba(56,189,248,0.12),transparent_45%)]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(148,163,184,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.07)_1px,transparent_1px)] mask-[radial-gradient(circle_at_center,black,transparent_70%)] bg-size-[48px_48px]"
      />

      <motion.div
        className="relative h-[46vh] max-h-115 min-h-65 w-full max-w-xl"
        initial={reducedMotion ? false : { opacity: 0, y: 24, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, ease: EASE_OUT }}
      >
        <div ref={headSlotRef} className="h-full w-full" />
      </motion.div>

      <motion.div
        className="relative mt-2 flex flex-col items-center px-6 text-center"
        initial={reducedMotion ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 0.25, ease: EASE_OUT }}
      >
        <p className="mb-3 text-sm font-semibold tracking-[0.2em] text-teal-400 uppercase">
          Safety Assistant
        </p>
        <h1
          id="landing-title"
          className="text-4xl font-semibold tracking-tight text-balance sm:text-6xl"
        >
          Hi, I&apos;m here to keep you safe.
        </h1>
        <p className="mt-4 max-w-md text-base leading-7 text-pretty text-slate-400 sm:text-lg">
          Ask me about product and vehicle recalls, grounded in official NHTSA
          and CPSC data.
        </p>

        <Button
          ref={buttonRef}
          onClick={onEnter}
          disabled={entering}
          className="group mt-8 h-12 rounded-full bg-teal-500 px-7 text-base font-semibold text-slate-950 shadow-[0_0_40px_-8px_rgba(45,212,191,0.8)] hover:bg-teal-400 focus-visible:ring-teal-300 disabled:opacity-100 dark:bg-teal-500 dark:text-slate-950 dark:hover:bg-teal-400"
        >
          Enter
          <ArrowRight
            className="size-5 transition-transform group-hover:translate-x-1"
            aria-hidden="true"
          />
        </Button>
        <p className="mt-4 text-xs text-slate-500">
          or press <kbd className="font-sans font-semibold">Esc</kbd> to skip
        </p>
      </motion.div>
    </motion.div>
  );
}
