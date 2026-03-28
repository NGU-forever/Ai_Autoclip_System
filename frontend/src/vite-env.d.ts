/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  /** qiankun 子应用 entry：开发一般为 http://localhost:5174，生产为同源 /uploader-ui/ */
  readonly VITE_UPLOADER_QIANKUN_ENTRY?: string;
  /** qiankun OpenStoryline entry：开发一般为 http://localhost:5175，生产为同源 /openstoryline-ui/ */
  readonly VITE_OPENSTORYLINE_QIANKUN_ENTRY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

