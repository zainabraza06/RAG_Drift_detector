/// <reference types="vite/client" />

/** Typed build-time configuration, so `import.meta.env` is not `any`. */
interface ImportMetaEnv {
  /** Overrides the API base path. Defaults to "/api" (same-origin). */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
