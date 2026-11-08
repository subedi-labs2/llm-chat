import { useEffect, useState } from "react";

import { getHealth, type HealthResponse } from "@/lib/api";

export type ApiStatus = "checking" | "connected" | "unavailable";

const POLL_INTERVAL_MS = 3_000;
const REQUEST_TIMEOUT_MS = 2_000;

export interface ApiState {
  status: ApiStatus;
  /** The latest health response, kept while the API is briefly unavailable. */
  health: HealthResponse | null;
}

export function useApiStatus(): ApiState {
  const [status, setStatus] = useState<ApiStatus>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let controller: AbortController | undefined;
    let timeoutId: number | undefined;
    let intervalId: number | undefined;

    const check = () => {
      const previous = controller;
      const current = new AbortController();
      controller = current;
      previous?.abort();
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(() => current.abort(), REQUEST_TIMEOUT_MS);

      getHealth(current.signal)
        .then((response) => {
          if (controller === current) {
            setStatus("connected");
            // Keep the same object while unchanged so polling doesn't re-render.
            setHealth((previous) =>
              previous?.version === response.version &&
              previous.commit === response.commit
                ? previous
                : response,
            );
          }
        })
        .catch(() => {
          // Only the active check may report failure; superseded or cancelled checks are ignored.
          if (controller === current) {
            setStatus("unavailable");
          }
        })
        .finally(() => {
          if (controller === current) {
            window.clearTimeout(timeoutId);
          }
        });
    };

    const startPolling = () => {
      window.clearInterval(intervalId);
      if (document.visibilityState !== "visible") {
        return;
      }
      check();
      intervalId = window.setInterval(check, POLL_INTERVAL_MS);
    };

    const stopPolling = () => {
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
      const active = controller;
      controller = undefined;
      active?.abort();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        startPolling();
      } else {
        stopPolling();
      }
    };

    const handleOffline = () => setStatus("unavailable");

    startPolling();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", startPolling);
    window.addEventListener("offline", handleOffline);

    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("online", startPolling);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  return { status, health };
}
