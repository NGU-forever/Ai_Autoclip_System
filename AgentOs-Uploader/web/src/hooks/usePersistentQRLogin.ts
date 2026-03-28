// ========================================
// 分发页扫码：按需 qr-login（单任务浏览器，用完即关）
// 对外仍使用 Persistent* 类型名以兼容 VideoDistributor / QRLoginModal
// ========================================

import { useState, useEffect, useRef, useCallback } from 'react';
import { getToken } from '../lib/http';
import {
  startQRLogin,
  getQRCodeUrl,
  getQRLoginStatus,
  cancelQRLogin,
  type QRLoginStatus,
} from './useUploader';

// ===== Types =====

export type PersistentPlatform = 'douyin' | 'tencent' | 'xhs';

export interface PersistentSession {
  sessionId: string;
  platform: PersistentPlatform;
  status: 'initializing' | 'ready' | 'scanning' | 'success' | 'failed' | 'expired';
  qrUrl: string;
  message: string;
}

export interface PersistentSessionStatus {
  sessionId: string;
  platform: string;
  status: 'initializing' | 'ready' | 'scanning' | 'success' | 'failed' | 'expired';
  account?: {
    id: string;
    platform: PersistentPlatform;
    userName: string;
    cookieFile: string;
    status: number;
  };
  error?: string;
}

// ===== Constants =====

const PLATFORMS: PersistentPlatform[] = ['douyin', 'tencent', 'xhs'];

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

function mapTaskStatusToModal(
  s: QRLoginStatus['status'] | undefined
): PersistentSession['status'] {
  switch (s) {
    case 'pending':
      return 'ready';
    case 'scanning':
      return 'scanning';
    case 'success':
      return 'success';
    case 'expired':
      return 'expired';
    case 'failed':
    default:
      return 'failed';
  }
}

function toPersistentSessionStatus(st: QRLoginStatus): PersistentSessionStatus {
  return {
    sessionId: st.taskId,
    platform: st.platform,
    status: mapTaskStatusToModal(st.status),
    account: st.account,
    error: st.error,
  };
}

// ===== Hook =====

export interface UsePersistentQRLoginReturn {
  sessions: Record<PersistentPlatform, PersistentSession | null>;
  loading: Record<PersistentPlatform, boolean>;
  errors: Record<PersistentPlatform, string | null>;
  /** 用户点击某平台扫码时调用：取消旧任务并启动新的 qr-login */
  requestQRLogin: (platform: PersistentPlatform) => Promise<void>;
  refreshQR: (platform: PersistentPlatform) => Promise<string | null>;
  refreshAllPersistentQR: () => Promise<boolean>;
  closeSession: (platform: PersistentPlatform) => Promise<void>;
  checkStatus: (platform: PersistentPlatform) => Promise<PersistentSessionStatus | null>;
  reinitSession: (platform: PersistentPlatform) => Promise<void>;
}

const emptySessions = (): Record<PersistentPlatform, PersistentSession | null> => ({
  douyin: null,
  tencent: null,
  xhs: null,
});

const emptyLoading = (): Record<PersistentPlatform, boolean> => ({
  douyin: false,
  tencent: false,
  xhs: false,
});

const emptyErrors = (): Record<PersistentPlatform, string | null> => ({
  douyin: null,
  tencent: null,
  xhs: null,
});

export function usePersistentQRLogin(): UsePersistentQRLoginReturn {
  const [sessions, setSessions] = useState<Record<PersistentPlatform, PersistentSession | null>>(
    emptySessions
  );
  const [loading, setLoading] = useState<Record<PersistentPlatform, boolean>>(emptyLoading);
  const [errors, setErrors] = useState<Record<PersistentPlatform, string | null>>(emptyErrors);

  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const cancelActiveTask = useCallback(async (platform: PersistentPlatform) => {
    const existing = sessionsRef.current[platform];
    if (!existing?.sessionId || existing.status === 'success') {
      return;
    }
    try {
      await cancelQRLogin(existing.sessionId);
    } catch {
      /* ignore */
    }
  }, []);

  const startOrRestartLogin = useCallback(
    async (platform: PersistentPlatform) => {
      setLoading(prev => ({ ...prev, [platform]: true }));
      setErrors(prev => ({ ...prev, [platform]: null }));
      await cancelActiveTask(platform);
      setSessions(prev => ({ ...prev, [platform]: null }));
      try {
        const task = await startQRLogin(platform);
        const sess: PersistentSession = {
          sessionId: task.taskId,
          platform,
          status: mapTaskStatusToModal(task.status),
          qrUrl: task.qrUrl || getQRCodeUrl(task.taskId),
          message: task.message || '',
        };
        setSessions(prev => ({ ...prev, [platform]: sess }));
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : '启动扫码失败';
        setErrors(prev => ({ ...prev, [platform]: errorMsg }));
        console.error(`Failed to start QR login for ${platform}:`, err);
      } finally {
        setLoading(prev => ({ ...prev, [platform]: false }));
      }
    },
    [cancelActiveTask]
  );

  const requestQRLogin = useCallback(
    async (platform: PersistentPlatform) => {
      await startOrRestartLogin(platform);
    },
    [startOrRestartLogin]
  );

  useEffect(() => {
    const cancelAllOpen = () => {
      const cur = sessionsRef.current;
      for (const p of PLATFORMS) {
        const s = cur[p];
        if (s?.sessionId && s.status !== 'success') {
          fireKeepaliveCancelQRLogin(s.sessionId);
        }
      }
    };

    const onLeave = () => {
      cancelAllOpen();
    };

    window.addEventListener('beforeunload', onLeave);
    window.addEventListener('pagehide', onLeave);

    return () => {
      window.removeEventListener('beforeunload', onLeave);
      window.removeEventListener('pagehide', onLeave);
      cancelAllOpen();
    };
  }, []);

  const refreshQR = useCallback(
    async (platform: PersistentPlatform): Promise<string | null> => {
      const session = sessionsRef.current[platform];
      if (!session?.sessionId) {
        return null;
      }

      setLoading(prev => ({ ...prev, [platform]: true }));
      setErrors(prev => ({ ...prev, [platform]: null }));

      try {
        setSessions(prev => ({
          ...prev,
          [platform]: { ...session, status: 'initializing' },
        }));
        await cancelQRLogin(session.sessionId);
        const task = await startQRLogin(platform);
        const newSession: PersistentSession = {
          sessionId: task.taskId,
          platform,
          status: mapTaskStatusToModal(task.status),
          qrUrl: task.qrUrl || getQRCodeUrl(task.taskId),
          message: task.message || '',
        };
        setSessions(prev => ({ ...prev, [platform]: newSession }));
        return `${newSession.qrUrl}?t=${Date.now()}`;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : '刷新失败';
        setErrors(prev => ({ ...prev, [platform]: errorMsg }));
        setSessions(prev => ({ ...prev, [platform]: session }));
        return null;
      } finally {
        setLoading(prev => ({ ...prev, [platform]: false }));
      }
    },
    []
  );

  const refreshAllPersistentQR = useCallback(async (): Promise<boolean> => {
    return true;
  }, []);

  const closeSession = useCallback(async (platform: PersistentPlatform) => {
    const session = sessionsRef.current[platform];
    if (!session?.sessionId) {
      return;
    }
    if (session.status !== 'success') {
      try {
        await cancelQRLogin(session.sessionId);
      } catch (err) {
        console.warn(`cancelQRLogin ${platform}:`, err);
      }
    }
    setSessions(prev => ({ ...prev, [platform]: null }));
  }, []);

  const checkStatus = useCallback(
    async (platform: PersistentPlatform): Promise<PersistentSessionStatus | null> => {
      const session = sessionsRef.current[platform];
      if (!session?.sessionId) {
        return null;
      }

      try {
        const st = await getQRLoginStatus(session.sessionId);
        const mapped = mapTaskStatusToModal(st.status);
        if (mapped !== session.status) {
          setSessions(prev => ({
            ...prev,
            [platform]: { ...session, status: mapped },
          }));
        }
        return toPersistentSessionStatus(st);
      } catch (err) {
        console.error(`Failed to check ${platform} status:`, err);
        return null;
      }
    },
    []
  );

  const reinitSession = useCallback(
    async (platform: PersistentPlatform) => {
      await startOrRestartLogin(platform);
    },
    [startOrRestartLogin]
  );

  return {
    sessions,
    loading,
    errors,
    requestQRLogin,
    refreshQR,
    refreshAllPersistentQR,
    closeSession,
    checkStatus,
    reinitSession,
  };
}
