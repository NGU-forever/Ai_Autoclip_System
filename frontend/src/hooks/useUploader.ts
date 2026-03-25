// ========================================
// Video Distributor - Uploader API Hooks
// ========================================

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  http,
  getToken,
  clearAuth,
  API_BASE,
  convertKeysToSnake,
  convertKeysToCamel,
} from '../core/api/http';

// ===== Types =====

export interface VideoItem {
  id: string;
  filename: string;
  filePath: string;
  sizeMb?: number;
  createdAt?: string;
}

export interface Account {
  id: string;
  platform: 'douyin' | 'tencent' | 'xhs';
  userName: string;
  cookieFile: string;
  status: number;
}

export interface Platform {
  id: string;
  name: string;
}

export interface PublishParams {
  platform: 'douyin' | 'tencent' | 'xhs';
  accountId: string;
  videoId: string;
  title: string;
  tags: string[];
  // 视频号
  category?: string;
  isDraft?: boolean;
  shortTitle?: string;
  declareOriginal?: boolean;
  // 抖音
  thumbnailPath?: string;
  productLink?: string;
  productTitle?: string;
  // 小红书
  desc?: string;
  coverPath?: string;
  isPrivate?: boolean;
  // 通用
  publishDate?: string; // ISO 8601 格式
}

export interface PublishResponse {
  success: boolean;
  message: string;
  taskId?: string;
}

/** 发布前 Cookie 校验失败（后端 409 UPLOADER_COOKIE_INVALID） */
export class UploaderCookieInvalidError extends Error {
  readonly code = 'UPLOADER_COOKIE_INVALID' as const;

  constructor(
    message: string,
    public readonly platform: string,
  ) {
    super(message);
    this.name = 'UploaderCookieInvalidError';
  }
}

export interface QRLoginTask {
  taskId: string;
  status: 'pending' | 'scanning' | 'success' | 'failed' | 'expired';
  message: string;
  qrUrl?: string;  // 后端返回的二维码 URL
}

export interface QRLoginStatus {
  taskId: string;
  status: 'pending' | 'scanning' | 'success' | 'failed' | 'expired';
  platform: string;
  account?: Account;
  error?: string;
}

// ===== API Functions =====

export async function listVideos(): Promise<VideoItem[]> {
  const response = await http.get<{ items: VideoItem[]; total: number }>('/uploader/videos');
  return response.items;
}

export async function uploadVideo(file: File): Promise<VideoItem> {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch('/api/admin/uploader/videos', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
    },
    body: formData,
  });
  
  if (!response.ok) {
    throw new Error('上传失败');
  }
  
  return await response.json();
}

export async function uploadCover(file: File): Promise<VideoItem> {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch('/api/admin/uploader/upload-cover', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
    },
    body: formData,
  });
  
  if (!response.ok) {
    throw new Error('封面上传失败');
  }
  
  return await response.json();
}

export async function listAccounts(): Promise<Account[]> {
  return await http.get<Account[]>('/uploader/accounts');
}

export async function addAccount(
  platform: string,
  userName: string,
  cookieFile: File
): Promise<Account> {
  const formData = new FormData();
  formData.append('platform', platform);
  formData.append('user_name', userName);
  formData.append('file', cookieFile);
  
  const response = await fetch('/api/admin/uploader/accounts', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
    },
    body: formData,
  });
  
  if (!response.ok) {
    throw new Error('添加账号失败');
  }
  
  return await response.json();
}

export async function deleteAccount(id: string): Promise<void> {
  await http.delete(`/uploader/accounts/${id}`);
}

export async function publish(params: PublishParams): Promise<PublishResponse> {
  const token = getToken();
  const response = await fetch(`${API_BASE}/uploader/publish`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(convertKeysToSnake(params)),
  });

  if (response.status === 401) {
    clearAuth();
    window.location.href = '/login';
    throw new Error('未授权，请重新登录');
  }

  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as {
      detail?: string | { code?: string; platform?: string; message?: string };
    };
    const detail = data.detail;
    if (
      response.status === 409 &&
      detail &&
      typeof detail === 'object' &&
      !Array.isArray(detail) &&
      detail.code === 'UPLOADER_COOKIE_INVALID'
    ) {
      throw new UploaderCookieInvalidError(
        detail.message || '登录已失效，请重新扫码登录',
        detail.platform || '',
      );
    }
    let errorMessage = `请求失败 (${response.status})`;
    if (typeof detail === 'string') {
      errorMessage = detail;
    }
    throw new Error(errorMessage);
  }

  const data = await response.json();
  return convertKeysToCamel(data) as PublishResponse;
}

export async function listPlatforms(): Promise<Platform[]> {
  const response = await http.get<{ platforms: Platform[] }>('/uploader/platforms');
  return response.platforms;
}

// ===== 扫码登录 API =====

export async function startQRLogin(platform: string): Promise<QRLoginTask> {
  return await http.post<QRLoginTask>(`/uploader/accounts/qr-login?platform=${platform}`);
}

export function getQRCodeUrl(taskId: string): string {
  return `/api/admin/uploader/accounts/qr-login/${taskId}/qr-code`;
}

export async function getQRLoginStatus(taskId: string): Promise<QRLoginStatus> {
  return await http.get<QRLoginStatus>(`/uploader/accounts/qr-login/${taskId}/status`);
}

export async function cancelQRLogin(taskId: string): Promise<void> {
  await http.post(`/uploader/accounts/qr-login/${taskId}/cancel`);
}

const QR_LOGIN_CANCEL_URL = (taskId: string) =>
  `/api/admin/uploader/accounts/qr-login/${taskId}/cancel`;

function fireKeepaliveCancelQRLogin(taskId: string): void {
  const token = getToken();
  if (!token) return;
  fetch(QR_LOGIN_CANCEL_URL(taskId), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    keepalive: true,
  }).catch(() => {});
}

// ===== 持久化扫码登录 API =====

export async function initPersistentSession(platform: string): Promise<{
  sessionId: string;
  platform: string;
  status: string;
  qrUrl: string;
  message: string;
}> {
  return await http.post(`/uploader/accounts/qr-persistent/init?platform=${platform}`);
}

export async function refreshPersistentQR(sessionId: string): Promise<{ success: boolean; status?: string }> {
  return await http.post(`/uploader/accounts/qr-persistent/${sessionId}/refresh-qr`);
}

export async function getPersistentSessionStatus(sessionId: string): Promise<{
  sessionId: string;
  platform: string;
  status: string;
  account?: Account;
  error?: string;
}> {
  return await http.get(`/uploader/accounts/qr-persistent/${sessionId}/status`);
}

export async function closePersistentSession(sessionId: string): Promise<void> {
  await http.post(`/uploader/accounts/qr-persistent/${sessionId}/cancel`);
}

export function getPersistentQRCodeUrl(sessionId: string): string {
  return `/api/admin/uploader/accounts/qr-persistent/${sessionId}/qr-code`;
}

// ===== React Hooks =====

export function useVideos() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listVideos();
      setVideos(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取视频列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  return { videos, loading, error, fetchVideos };
}

export function useAccounts() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAccounts();
      setAccounts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取账号列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const addNewAccount = useCallback(async (platform: string, userName: string, cookieFile: File) => {
    const newAccount = await addAccount(platform, userName, cookieFile);
    setAccounts((prev) => [...prev, newAccount]);
    return newAccount;
  }, []);

  const addNewAccountByQR = useCallback((account: Account) => {
    setAccounts((prev) => [...prev, account]);
  }, []);

  const removeAccount = useCallback(async (id: string) => {
    await deleteAccount(id);
    setAccounts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  return { accounts, loading, error, fetchAccounts, addNewAccount, addNewAccountByQR, removeAccount };
}

// ===== 扫码登录 Hook =====

export function useQRLogin() {
  const [task, setTask] = useState<QRLoginTask | null>(null);
  const [status, setStatus] = useState<QRLoginStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);

  const taskRef = useRef<{ taskId: string | null; st: string | null }>({
    taskId: null,
    st: null,
  });

  useEffect(() => {
    const taskId = task?.taskId ?? null;
    const st = (status?.status ?? task?.status) ?? null;
    taskRef.current = { taskId, st };
  }, [task, status]);

  useEffect(() => {
    return () => {
      const { taskId, st } = taskRef.current;
      if (taskId && st && st !== 'success') {
        fireKeepaliveCancelQRLogin(taskId);
      }
    };
  }, []);

  useEffect(() => {
    const onLeave = () => {
      const { taskId, st } = taskRef.current;
      if (taskId && st && st !== 'success') {
        fireKeepaliveCancelQRLogin(taskId);
      }
    };
    window.addEventListener('beforeunload', onLeave);
    window.addEventListener('pagehide', onLeave);
    return () => {
      window.removeEventListener('beforeunload', onLeave);
      window.removeEventListener('pagehide', onLeave);
    };
  }, []);

  const startLogin = useCallback(async (platform: string) => {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      const newTask = await startQRLogin(platform);
      setTask(newTask);
      // 优先使用后端返回的 qr_url，减少前端硬编码
      setQrUrl(newTask.qrUrl || getQRCodeUrl(newTask.taskId));
      return newTask;
    } catch (err) {
      setError(err instanceof Error ? err.message : '启动扫码登录失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const checkStatus = useCallback(async (taskId: string) => {
    try {
      const currentStatus = await getQRLoginStatus(taskId);
      setStatus(currentStatus);
      return currentStatus;
    } catch (err) {
      setError(err instanceof Error ? err.message : '查询登录状态失败');
      return null;
    }
  }, []);

  const cancelLogin = useCallback(async (taskId: string) => {
    try {
      await cancelQRLogin(taskId);
      setTask(null);
      setStatus(null);
      setQrUrl(null);
    } catch (err) {
      console.warn('取消登录失败:', err);
    }
  }, []);

  const reset = useCallback(() => {
    setTask(null);
    setStatus(null);
    setQrUrl(null);
    setError(null);
  }, []);

  /** 使用分发页预请求的 taskId/qrUrl 填充状态，打开弹窗时无需再等一轮 POST */
  const applyPrefetch = useCallback((p: { taskId: string; qrUrl?: string }) => {
    setError(null);
    setStatus(null);
    setTask({
      taskId: p.taskId,
      status: 'pending',
      message: '',
    });
    setQrUrl(p.qrUrl || getQRCodeUrl(p.taskId));
  }, []);

  return {
    task,
    status,
    loading,
    error,
    qrUrl,
    startLogin,
    checkStatus,
    cancelLogin,
    reset,
    applyPrefetch,
  };
}

export function usePublish() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submitPublish = useCallback(async (params: PublishParams): Promise<PublishResponse | null> => {
    setLoading(true);
    setError(null);
    try {
      const response = await publish(params);
      return response;
    } catch (err) {
      if (err instanceof UploaderCookieInvalidError) {
        throw err;
      }
      setError(err instanceof Error ? err.message : '发布失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { loading, error, submitPublish };
}
