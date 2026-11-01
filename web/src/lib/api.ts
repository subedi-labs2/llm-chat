export interface HealthResponse {
  status: "ok";
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch("/api/health", { signal });

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return (await response.json()) as HealthResponse;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatSource {
  id: string;
  agency: "NHTSA" | "CPSC";
  title: string;
  url: string;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
}

export class ChatError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`Chat failed with status ${status}`);
    this.name = "ChatError";
    this.status = status;
  }
}

export async function sendChat(
  messages: ChatMessage[],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });

  if (!response.ok) {
    throw new ChatError(response.status);
  }

  return (await response.json()) as ChatResponse;
}
