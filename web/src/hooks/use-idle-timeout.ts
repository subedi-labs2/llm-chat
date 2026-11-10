import { useEffect, useRef } from "react";

const ACTIVITY_EVENTS = [
  "pointerdown",
  "pointermove",
  "keydown",
  "wheel",
  "touchstart",
  "scroll",
] as const;

/** Calls `onIdle` once after `timeoutMs` without user activity while `enabled`. */
export function useIdleTimeout(
  enabled: boolean,
  timeoutMs: number,
  onIdle: () => void,
) {
  const onIdleRef = useRef(onIdle);
  useEffect(() => {
    onIdleRef.current = onIdle;
  }, [onIdle]);

  useEffect(() => {
    if (!enabled || timeoutMs <= 0) return;

    let timer = window.setTimeout(() => onIdleRef.current(), timeoutMs);
    function reset() {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => onIdleRef.current(), timeoutMs);
    }

    // Capture so scrolls inside nested containers (which don't bubble) count too.
    const options = { capture: true, passive: true };
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, reset, options);
    }
    return () => {
      window.clearTimeout(timer);
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, reset, options);
      }
    };
  }, [enabled, timeoutMs]);
}
