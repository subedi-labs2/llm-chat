import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Theme } from "@/hooks/use-theme";

interface ThemeToggleProps {
  value: Theme;
  onChange: (theme: Theme) => void;
}

export function ThemeToggle({ value, onChange }: ThemeToggleProps) {
  const dark = value === "dark";
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      aria-label="Dark mode"
      aria-pressed={dark}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={() => onChange(dark ? "light" : "dark")}
      className="size-8"
    >
      {dark ? (
        <Moon className="size-4" aria-hidden="true" />
      ) : (
        <Sun className="size-4" aria-hidden="true" />
      )}
    </Button>
  );
}
