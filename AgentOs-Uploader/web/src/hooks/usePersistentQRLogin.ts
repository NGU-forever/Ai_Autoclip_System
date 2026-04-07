// ========================================
// 分发页扫码：按需 qr-login（单任务浏览器，用完即关）
// 使用 HTTP 轮询获取登录状态
// 对外仍使用 Persistent* 类型名以兼容 VideoDistributor / QRLoginModal
// ========================================

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  startQRLogin,
  getQRCodeUrl,
  getQRLoginStatus,
  cancelQRLogin,
  persistentHeartbeat,
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
  userName?: string;
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
  fetch(QR_LOGIN_CANCEL_URL(taskId), {
    method: 'POST',
    // 认证由 backend 统一处理，通过 cookie 传递
    credentials: 'include',
    keepalive: true,
  }).catch(() => {});
}

function mapTaskStatusToModal(
  s: QRLoginStatus['status'] | undefined
): PersistentSession['status'] {
  switch (s) {
    case 'initializing':
      return 'initializing';
    case 'ready':
      return 'ready';
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
  closeSession: (platform: PersistentPlatform) => void;
  /** 轮询检查状态 */
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

  // 心跳定时器：保持后端浏览器实例存活
  useEffect(() => {
    const timer = setInterval(() => {
      const cur = sessionsRef.current;
      for (const p of PLATFORMS) {
        const s = cur[p];
        // 只有正在进行的任务需要心跳
        if (s?.sessionId && s.status !== 'success' && s.status !== 'failed' && s.status !== 'expired') {
          // 这里使用异步调用但不等待，避免阻塞定时器
          persistentHeartbeat(s.sessionId).catch((e: Error) => console.warn(`Heartbeat for ${p} failed:`, e));
        }
      }
    }, 15000); // 每 15 秒发一次心跳

    return () => clearInterval(timer);
  }, []);

  // HTTP 轮询：通过 HTTP API 定期查询登录状态
  useEffect(() => {
    const pollTimer = setInterval(async () => {
      const cur = sessionsRef.current;
      for (const p of PLATFORMS) {
        const s = cur[p];
        // 只轮询活跃的、未完成的会话
        if (!s?.sessionId || s.status === 'success' || s.status === 'failed') {
          continue;
        }
        try {
          const st = await getQRLoginStatus(s.sessionId);
          const mapped = mapTaskStatusToModal(st.status);
          
          // 只在状态变化时更新
          if (mapped !== s.status) {
            console.log(`[HTTP Poll] ${p}: ${s.status} → ${mapped}`);
            setSessions(prev => ({
              ...prev,
              [p]: {
                ...s,
                status: mapped,
                userName: st.account?.userName || s.userName,
              },
            }));
          }
        } catch {
          // 轮询失败静默处理
        }
      }
    }, 3000); // 每 3 秒轮询一次

    return () => clearInterval(pollTimer);
  }, []);

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

  const closeSession = useCallback((platform: PersistentPlatform) => {
    const session = sessionsRef.current[platform];
    if (!session?.sessionId) {
      return;
    }
    if (session.status !== 'success') {
      try {
        cancelQRLogin(session.sessionId);
      } catch (err) {
        console.warn(`cancelQRLogin ${platform}:`, err);
      }
    }
    setSessions(prev => ({ ...prev, [platform]: null }));
  }, []);

  // checkStatus: 使用 HTTP API 获取登录状态
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
