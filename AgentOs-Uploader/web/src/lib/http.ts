// ========================================
// Uploader SPA — HTTP 客户端（与主站字段约定一致）
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

export function getToken(): string | null {
  return localStorage.getItem('access_token');
}

export function setToken(token: string): void {
  localStorage.setItem('access_token', token);
}

export function removeToken(): void {
  localStorage.removeItem('access_token');
}

export function setUser(user: Record<string, unknown>): void {
  localStorage.setItem('current_user', JSON.stringify(user));
}

export function getUser(): Record<string, unknown> | null {
  try {
    const raw = localStorage.getItem('current_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearAuth(): void {
  removeToken();
  localStorage.removeItem('current_user');
}

/** 无 token 或 401：跳转主站登录页，并带回跳 next（当前页，不含 hash） */
export function redirectToMainLogin(): void {
  clearAuth();
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

interface RequestOptions {
  skipAuth?: boolean;
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

  if (!options.skipAuth) {
    const token = getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const url = `${API_BASE}${path}`;

  const fetchOptions: RequestInit = {
    method,
    headers,
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
