// ========================================
// Uploader SPA — HTTP 客户端（认证由 backend 统一处理，使用 cookie）
// ========================================

export const API_BASE = '/api/admin';

function toSnakeCase(str: string): string {
  return str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

function toCamelCase(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

export function convertKeysToSnake(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(convertKeysToSnake);
  if (obj !== null && typeof obj === 'object' && !(obj instanceof Date)) {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [toSnakeCase(k), convertKeysToSnake(v)]),
    );
  }
  return obj;
}

export function convertKeysToCamel(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(convertKeysToCamel);
  if (obj !== null && typeof obj === 'object' && !(obj instanceof Date)) {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [toCamelCase(k), convertKeysToCamel(v)]),
    );
  }
  return obj;
}

/** 跳转主站登录页，并带回跳 next（当前页，不含 hash） */
export function redirectToMainLogin(): void {
  const login = import.meta.env.VITE_LOGIN_PAGE_URL || 'http://localhost/login';
  const next = window.location.origin + window.location.pathname + window.location.search;
  try {
    // 改用更宽松的URL验证，支持0.0.0.0等特殊地址
    let u: URL;
    if (!login.startsWith('http://') && !login.startsWith('https://')) {
      // 特殊处理0.0.0.0和localhost
      if (login.startsWith('0.0.0.0:') || login.startsWith('127.0.0.1:') || login.startsWith('localhost:')) {
        u = new URL(`http://${login}`);
      } else {
        throw new Error('Invalid URL scheme');
      }
    } else {
      u = new URL(login);
    }
    u.searchParams.set('next', next);
    window.location.replace(u.toString());
  } catch {
    window.location.replace(login);
  }
}

/** 清除认证信息（跳转登录页前调用） */
export function clearAuth(): void {
  // 认证由 backend 管理，这里只负责跳转
  redirectToMainLogin();
}

interface RequestOptions {
  skipConvert?: boolean;
  rawResponse?: boolean;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  const url = `${API_BASE}${path}`;

  const fetchOptions: RequestInit = {
    method,
    headers,
    // 包含 cookie（由 backend 统一处理认证）
    credentials: 'include',
  };

  if (body !== undefined && method !== 'GET') {
    fetchOptions.body = JSON.stringify(options.skipConvert ? body : convertKeysToSnake(body));
  }

  const response = await fetch(url, fetchOptions);

  if (response.status === 401 && !path.startsWith('/auth/login')) {
    redirectToMainLogin();
    throw new Error('未授权，请重新登录');
  }

  if (!response.ok) {
    let errorMessage = `请求失败 (${response.status})`;
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorMessage;
    } catch {
      // ignore
    }
    throw new Error(errorMessage);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json();
  return (options.skipConvert ? data : convertKeysToCamel(data)) as T;
}

export const http = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>('GET', path, undefined, options);
  },
  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('POST', path, body, options);
  },
  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('PUT', path, body, options);
  },
  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('PATCH', path, body, options);
  },
  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>('DELETE', path, undefined, options);
  },
};
