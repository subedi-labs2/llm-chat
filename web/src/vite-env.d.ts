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
