/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  readonly VITE_UPLOADER_PUBLIC_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

