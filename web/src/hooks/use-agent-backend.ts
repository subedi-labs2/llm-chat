import { useEffect, useState } from "react";

import { getChatConfig, type AgentBackend } from "@/lib/api";

const STORAGE_KEY = "agent-backend";

function isAgentBackend(value: unknown): value is AgentBackend {
  return value === "pydantic_ai" || value === "langchain";
}

function storedBackend(): AgentBackend | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isAgentBackend(value) ? value : null;
  } catch {
    return null;
  }
}

export interface AgentBackendSelection {
  /** The backend to request, or null when the API doesn't allow choosing one. */
  backend: AgentBackend | null;
  setBackend: (backend: AgentBackend) => void;
}

export function useAgentBackend(apiConnected: boolean): AgentBackendSelection {
  const [loaded, setLoaded] = useState(false);
  const [backend, setBackendState] = useState<AgentBackend | null>(null);

  useEffect(() => {
    if (!apiConnected || loaded) return;
    const controller = new AbortController();
    getChatConfig(controller.signal)
      .then((config) => {
        setLoaded(true);
        if (config.backend_selection) {
          setBackendState(storedBackend() ?? config.default_backend);
        }
      })
      .catch(() => {
        // Retried on the next reconnect; until then the API's default backend is used.
      });
    return () => controller.abort();
  }, [apiConnected, loaded]);

  function setBackend(next: AgentBackend) {
    setBackendState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage can be unavailable (e.g. private mode); the choice still applies this session.
    }
  }

  return { backend, setBackend };
}
