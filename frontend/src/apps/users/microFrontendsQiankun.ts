import { registerMicroApps, start } from 'qiankun';

let started = false;

function resolveUploaderEntry(): string {
  const env = import.meta.env.VITE_UPLOADER_QIANKUN_ENTRY?.trim();
  if (env) return env;
  if (import.meta.env.DEV) return 'http://localhost:5174';
  return `${window.location.origin}/uploader-ui/`;
}

function resolveOpenStorylineEntry(): string {
  const env = import.meta.env.VITE_OPENSTORYLINE_QIANKUN_ENTRY?.trim();
  if (env) return env;
  if (import.meta.env.DEV) return 'http://localhost:5175';
  return `${window.location.origin}/openstoryline-ui/`;
}

/** 注册 uploader + openstoryline 子应用并只启动一次 qiankun */
export function startUserMicroFrontends(): void {
  if (started) return;
  started = true;

  registerMicroApps([
    {
      name: 'uploader',
      entry: resolveUploaderEntry(),
      container: '#uploader-subapp',
      activeRule: (location) => location.pathname.startsWith('/distribute'),
      props: {
        get accessToken() {
          return localStorage.getItem('access_token') || undefined;
        },
        routerBasename: '/distribute',
      },
    },
    {
      name: 'openstoryline',
      entry: resolveOpenStorylineEntry(),
      container: '#openstoryline-subapp',
      activeRule: (location) => location.pathname.startsWith('/clip'),
      props: {
        routerBasename: '/clip',
      },
    },
  ]);

  start({ sandbox: false });
}
