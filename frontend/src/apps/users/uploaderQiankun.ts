import { registerMicroApps, start } from 'qiankun';

let started = false;

function resolveEntry(): string {
  const env = import.meta.env.VITE_UPLOADER_QIANKUN_ENTRY?.trim();
  if (env) return env;
  if (import.meta.env.DEV) return 'http://localhost:5174';
  return `${window.location.origin}/uploader-ui/`;
}

/** 在应用根部调用一次：注册子应用并启动 qiankun 路由监听 */
export function startUploaderQiankun(): void {
  if (started) return;
  started = true;

  registerMicroApps([
    {
      name: 'uploader',
      entry: resolveEntry(),
      container: '#uploader-subapp',
      activeRule: (location) => location.pathname.startsWith('/distribute'),
      props: {
        get accessToken() {
          return localStorage.getItem('access_token') || undefined;
        },
        routerBasename: '/distribute',
      },
    },
  ]);

  // Vite 子应用为 ES 模块，与严格 JS 沙箱易冲突；样式隔离可选后续再开
  start({ sandbox: false });
}
