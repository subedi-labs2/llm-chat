/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Release version of this build, set by the image build. */
  readonly VITE_APP_VERSION?: string;
  /** Git commit of this build, set by the image build. */
  readonly VITE_APP_COMMIT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  /** Runtime settings loaded from /config.js before the app starts. */
  APP_CONFIG?: {
    themeToggle?: boolean;
    idleTimeoutSeconds?: number;
  };
}
