// ========================================
// AgentOS Enterprise - HTTP 客户端
// 统一封装后端 API 请求
// ========================================

export const API_BASE = '/api/admin';

// ---- snake_case ↔ camelCase 转换 ----

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
            Object.entries(obj as Record<string, unknown>).map(([k, v]) => [toSnakeCase(k), convertKeysToSnake(v)])
        );
    }
    return obj;
}

export function convertKeysToCamel(obj: unknown): unknown {
    if (Array.isArray(obj)) return obj.map(convertKeysToCamel);
    if (obj !== null && typeof obj === 'object' && !(obj instanceof Date)) {
        return Object.fromEntries(
            Object.entries(obj as Record<string, unknown>).map(([k, v]) => [toCamelCase(k), convertKeysToCamel(v)])
        );
    }
    return obj;
}

// ---- Token 管理 ----

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

// ---- 核心请求函数 ----

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
        fetchOptions.body = JSON.stringify(
            options.skipConvert ? body : convertKeysToSnake(body)
        );
    }

    const response = await fetch(url, fetchOptions);

    // 401 → 跳转登录（但登录接口本身返回 401 不跳转）
    if (response.status === 401 && !path.startsWith('/auth/login')) {
        clearAuth();
        window.location.href = '/login';
        throw new Error('未授权，请重新登录');
    }

    if (!response.ok) {
        let errorMessage = `请求失败 (${response.status})`;
        try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorMessage;
        } catch {
            // 无法解析错误体
        }
        throw new Error(errorMessage);
    }

    // 204 No Content
    if (response.status === 204) {
        return undefined as T;
    }

    const data = await response.json();
    return (options.skipConvert ? data : convertKeysToCamel(data)) as T;
}

// ---- 便捷方法 ----

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
