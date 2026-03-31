import { qiankunWindow } from 'vite-plugin-qiankun/dist/helper';
import { getToken, setToken } from './http';

export type AuthBootstrapOptions = {
  /** 基座 qiankun props 注入，优先于 hash */
  accessToken?: string;
};

/**
 * 鉴权引导：基座 token > hash 回传；独立运行时无 token 则跳转主站登录。
 * qiankun 内无 token 时不整页跳转（由基座 RequireAuth / beforeLoad 保证）。
 */
export function bootstrapUploaderAuth(options: AuthBootstrapOptions = {}): void {
  const fromHost = options.accessToken?.trim();
  if (fromHost) {
    setToken(fromHost);
  }

  const raw = window.location.hash.replace(/^#/, '');
  if (raw) {
    const params = new URLSearchParams(raw);
    const token = params.get('access_token');
    if (token) {
      setToken(token);
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  if (getToken()) return;

  if (qiankunWindow.__POWERED_BY_QIANKUN__) {
    return;
  }

  const login = import.meta.env.VITE_LOGIN_PAGE_URL || 'http://localhost/login';
  const next = window.location.origin + window.location.pathname + window.location.search;
  try {
    const u = new URL(login);
    u.searchParams.set('next', next);
    window.location.replace(u.toString());
  } catch {
    window.location.replace(login);
  }
}
