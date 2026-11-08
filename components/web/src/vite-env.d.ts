/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `mock` (default) or `http`. See src/api/index.ts. */
  readonly VITE_API_MODE?: 'mock' | 'http';
  /** Base URL of the FastAPI backend when VITE_API_MODE=http. */
  readonly VITE_API_BASE_URL?: string;
  /** Login pre-filled and shown as the demo hint. Defaults to the mock demo user. */
  readonly VITE_DEMO_EMAIL?: string;
  readonly VITE_DEMO_PASSWORD?: string;
}
