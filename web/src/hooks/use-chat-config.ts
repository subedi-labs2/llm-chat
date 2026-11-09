import { useEffect, useState } from "react";

import { getChatConfig, type ChatConfig } from "@/lib/api";

const CONFIG_RETRY_MS = 3_000;

/** Loads the chat config once the API is connected; null until it loads. */
export function useChatConfig(apiConnected: boolean): ChatConfig | null {
  const [config, setConfig] = useState<ChatConfig | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!apiConnected || config) return;
    const controller = new AbortController();
    let retryId: number | undefined;
    getChatConfig(controller.signal)
      .then(setConfig)
      .catch(() => {
        // Until the config loads, the API's defaults apply.
        if (controller.signal.aborted) return;
        retryId = window.setTimeout(
          () => setAttempt((n) => n + 1),
          CONFIG_RETRY_MS,
        );
      });
    return () => {
      controller.abort();
      window.clearTimeout(retryId);
    };
  }, [apiConnected, config, attempt]);

  return config;
}
