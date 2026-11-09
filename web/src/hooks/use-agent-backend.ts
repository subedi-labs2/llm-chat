import { useState } from "react";

import type { AgentBackend, ChatConfig } from "@/lib/api";

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

export function useAgentBackend(
  config: ChatConfig | null,
): AgentBackendSelection {
  const [chosen, setChosen] = useState<AgentBackend | null>(storedBackend);

  function setBackend(next: AgentBackend) {
    setChosen(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage can be unavailable (e.g. private mode); the choice still applies this session.
    }
  }

  const backend = config?.backend_selection
    ? (chosen ?? config.default_backend)
    : null;
  return { backend, setBackend };
}
