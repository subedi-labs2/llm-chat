import { Button } from "@/components/ui/button";
import { AGENT_BACKEND_LABELS, type AgentBackend } from "@/lib/api";

const BACKENDS = Object.keys(AGENT_BACKEND_LABELS) as AgentBackend[];

interface BackendToggleProps {
  value: AgentBackend;
  onChange: (backend: AgentBackend) => void;
}

export function BackendToggle({ value, onChange }: BackendToggleProps) {
  return (
    <div
      role="group"
      aria-label="Agent framework"
      className="flex items-center gap-0.5 rounded-lg border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-700 dark:bg-slate-900"
    >
      {BACKENDS.map((backend) => {
        const selected = backend === value;
        return (
          <Button
            key={backend}
            type="button"
            variant={selected ? "default" : "outline"}
            aria-pressed={selected}
            onClick={() => onChange(backend)}
            className={`h-7 rounded-md px-2.5 text-xs ${
              selected
                ? ""
                : "border-transparent bg-transparent dark:bg-transparent"
            }`}
          >
            {AGENT_BACKEND_LABELS[backend]}
          </Button>
        );
      })}
    </div>
  );
}
