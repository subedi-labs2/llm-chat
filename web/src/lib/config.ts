/** Whether the header shows the light/dark theme toggle (set by the web chart's `themeToggle`). */

const DEFAULT_IDLE_TIMEOUT_SECONDS = 30;

function idleTimeoutSeconds(): number {
  const value = window.APP_CONFIG?.idleTimeoutSeconds;
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : DEFAULT_IDLE_TIMEOUT_SECONDS;
}

/** Inactivity before the landing page returns, in ms; 0 disables it (set by the web chart's `idleTimeoutSeconds`). */
export const IDLE_TIMEOUT_MS = idleTimeoutSeconds() * 1000;
export const THEME_TOGGLE_ENABLED = window.APP_CONFIG?.themeToggle === true;
