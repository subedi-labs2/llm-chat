export interface HealthResponse {
  status: "ok";
  version: string;
  commit: string;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch("/api/health", { signal });

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return (await response.json()) as HealthResponse;
}

export type AgentBackend = "pydantic_ai" | "langchain";

export const AGENT_BACKEND_LABELS: Record<AgentBackend, string> = {
  pydantic_ai: "Pydantic AI",
  langchain: "LangChain",
};

export interface ChatConfig {
  default_backend: AgentBackend;
  backend_selection: boolean;
}

export async function getChatConfig(signal?: AbortSignal): Promise<ChatConfig> {
  const response = await fetch("/api/chat/config", { signal });

  if (!response.ok) {
    throw new Error(`Chat config failed with status ${response.status}`);
  }

  return (await response.json()) as ChatConfig;
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
  backend: AgentBackend;
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
  backend: AgentBackend | null,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(backend ? { messages, backend } : { messages }),
    signal,
  });

  if (!response.ok) {
    throw new ChatError(response.status);
  }

  return (await response.json()) as ChatResponse;
}
