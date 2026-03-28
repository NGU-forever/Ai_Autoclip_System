/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LOGIN_PAGE_URL: string;
  readonly VITE_MAIN_APP_ORIGIN: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
