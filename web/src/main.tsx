import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { applyTheme, initialTheme } from "./hooks/use-theme";
import "./index.css";

// Apply the theme before the first render so the page doesn't flash light.
applyTheme(initialTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
