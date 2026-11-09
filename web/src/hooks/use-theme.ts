import { useState } from "react";

import { THEME_TOGGLE_ENABLED } from "@/lib/config";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";

function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

/** The theme to start with: light unless the toggle is enabled, then the saved or system theme. */
export function initialTheme(): Theme {
  if (!THEME_TOGGLE_ENABLED) return "light";
  return storedTheme() ?? systemTheme();
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export interface ThemeSelection {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

export function useTheme(): ThemeSelection {
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  function setTheme(next: Theme) {
    setThemeState(next);
    applyTheme(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage can be unavailable (e.g. private mode); the choice still applies this session.
    }
  }

  return { theme, setTheme };
}
