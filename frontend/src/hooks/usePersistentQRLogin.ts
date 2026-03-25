// ========================================
// Persistent QR Login Hook
// 管理后台常驻的浏览器会话（抖音 / 视频号 / 小红书）
// ========================================

import { useState, useEffect, useRef, useCallback } from 'react';
import { http, getToken } from '../core/api/http';

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

const HEARTBEAT_INTERVAL = 10000; // 10秒
const PLATFORMS: PersistentPlatform[] = ['douyin', 'tencent', 'xhs'];

const CLOSE_ALL_URL = '/api/admin/uploader/accounts/qr-persistent/close-all';

function fireKeepaliveCloseAll(): void {
  const token = getToken();
  if (!token) return;
  fetch(CLOSE_ALL_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    keepalive: true,
  }).catch(() => {});
}

// ===== API Functions =====

export async function initPersistentSession(platform: PersistentPlatform): Promise<PersistentSession> {
  return await http.post<PersistentSession>(`/uploader/accounts/qr-persistent/init?platform=${platform}`);
}

export async function sendHeartbeat(sessionId: string): Promise<{ success: boolean; status?: string }> {
  const response = await http.post<{ success: boolean; status?: string }>(
    `/uploader/accounts/qr-persistent/${sessionId}/heartbeat`
  );
  return response;
}

export async function refreshQRCode(sessionId: string): Promise<{ success: boolean; status?: string }> {
  const response = await http.post<{ success: boolean; status?: string }>(
    `/uploader/accounts/qr-persistent/${sessionId}/refresh-qr`
  );
  return response;
}

export async function getPersistentSessionStatus(sessionId: string): Promise<PersistentSessionStatus> {
  return await http.get<PersistentSessionStatus>(`/uploader/accounts/qr-persistent/${sessionId}/status`);
}

export async function closePersistentSession(sessionId: string): Promise<void> {
  await http.post(`/uploader/accounts/qr-persistent/${sessionId}/cancel`);
}

export async function closeAllPersistentSessions(): Promise<void> {
  await http.post('/uploader/accounts/qr-persistent/close-all');
}

export async function refreshAllPersistentSessionsApi(): Promise<{
  success: boolean;
  message: string;
  refreshed: number;
  skipped: number;
  errors: string[];
}> {
  return await http.post('/uploader/accounts/qr-persistent/refresh-all');
}

export function getPersistentQRCodeUrl(sessionId: string): string {
  return `/api/admin/uploader/accounts/qr-persistent/${sessionId}/qr-code`;
}

// ===== Hook =====

export interface UsePersistentQRLoginReturn {
  sessions: Record<PersistentPlatform, PersistentSession | null>;
  loading: Record<PersistentPlatform, boolean>;
  errors: Record<PersistentPlatform, string | null>;
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
  const [sessions, setSessions] = useState<Record<PersistentPlatform, PersistentSession | null>>(emptySessions);

  const [loading, setLoading] = useState<Record<PersistentPlatform, boolean>>(emptyLoading);

  const [errors, setErrors] = useState<Record<PersistentPlatform, string | null>>(emptyErrors);

  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const initSession = useCallback(async (platform: PersistentPlatform) => {
    setLoading(prev => ({ ...prev, [platform]: true }));
    setErrors(prev => ({ ...prev, [platform]: null }));

    try {
      const existingSession = sessionsRef.current[platform];
      if (existingSession?.sessionId) {
        try {
          await closePersistentSession(existingSession.sessionId);
        } catch {
          // 忽略关闭错误
        }
      }

      const session = await initPersistentSession(platform);
      setSessions(prev => ({ ...prev, [platform]: session }));
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '初始化失败';
      setErrors(prev => ({ ...prev, [platform]: errorMsg }));
      console.error(`Failed to init ${platform} session:`, err);
    } finally {
      setLoading(prev => ({ ...prev, [platform]: false }));
    }
  }, []);

  useEffect(() => {
    void Promise.all(PLATFORMS.map(p => initSession(p)));

    return () => {
      void closeAllPersistentSessions().catch(console.error);
    };
  }, [initSession]);

  useEffect(() => {
    const heartbeatInterval = setInterval(async () => {
      const currentSessions = sessionsRef.current;

      for (const platform of PLATFORMS) {
        const session = currentSessions[platform];
        if (session?.sessionId && session.status !== 'success') {
          try {
            const result = await sendHeartbeat(session.sessionId);
            if (result.status && result.status !== session.status) {
              setSessions(prev => ({
                ...prev,
                [platform]: { ...session, status: result.status as PersistentSession['status'] },
              }));
            }
          } catch (err) {
            console.warn(`Heartbeat failed for ${platform}:`, err);
          }
        }
      }
    }, HEARTBEAT_INTERVAL);

    return () => {
      clearInterval(heartbeatInterval);
    };
  }, []);

  useEffect(() => {
    const onLeave = () => {
      fireKeepaliveCloseAll();
    };

    window.addEventListener('beforeunload', onLeave);
    window.addEventListener('pagehide', onLeave);

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const currentSessions = sessionsRef.current;
        for (const platform of PLATFORMS) {
          const session = currentSessions[platform];
          if (session?.sessionId && session.status !== 'success') {
            sendHeartbeat(session.sessionId).catch(console.error);
          }
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('beforeunload', onLeave);
      window.removeEventListener('pagehide', onLeave);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const refreshQR = useCallback(async (platform: PersistentPlatform): Promise<string | null> => {
    const session = sessionsRef.current[platform];
    if (!session?.sessionId) {
      return null;
    }

    setLoading(prev => ({ ...prev, [platform]: true }));
    setErrors(prev => ({ ...prev, [platform]: null }));

    try {
      setSessions(prev => ({
        ...prev,
        [platform]: {
          ...session,
          status: 'initializing',
        },
      }));

      const result = await refreshQRCode(session.sessionId);

      if (result.success) {
        const newQrUrl = `${getPersistentQRCodeUrl(session.sessionId)}?t=${Date.now()}`;

        setSessions(prev => ({
          ...prev,
          [platform]: {
            ...session,
            qrUrl: newQrUrl,
            status: 'ready',
          },
        }));

        return newQrUrl;
      } else {
        setSessions(prev => ({
          ...prev,
          [platform]: session,
        }));
        return null;
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '刷新失败';
      setErrors(prev => ({ ...prev, [platform]: errorMsg }));
      setSessions(prev => ({
        ...prev,
        [platform]: session,
      }));
      return null;
    } finally {
      setLoading(prev => ({ ...prev, [platform]: false }));
    }
  }, []);

  const refreshAllPersistentQR = useCallback(async (): Promise<boolean> => {
    try {
      const res = await refreshAllPersistentSessionsApi();
      const ts = Date.now();
      setSessions(prev => {
        const next = { ...prev };
        for (const platform of PLATFORMS) {
          const s = next[platform];
          if (s?.sessionId && s.status !== 'success') {
            next[platform] = {
              ...s,
              qrUrl: `${getPersistentQRCodeUrl(s.sessionId)}?t=${ts}`,
            };
          }
        }
        return next;
      });
      for (const platform of PLATFORMS) {
        const s = sessionsRef.current[platform];
        if (!s?.sessionId) continue;
        try {
          const st = await getPersistentSessionStatus(s.sessionId);
          setSessions(prev => {
            const cur = prev[platform];
            if (!cur?.sessionId) return prev;
            return {
              ...prev,
              [platform]: {
                ...cur,
                status: st.status as PersistentSession['status'],
              },
            };
          });
        } catch {
          /* ignore */
        }
      }
      return res.success;
    } catch (e) {
      console.error('refresh-all failed:', e);
      return false;
    }
  }, []);

  const closeSession = useCallback(async (platform: PersistentPlatform) => {
    const session = sessionsRef.current[platform];
    if (!session?.sessionId) {
      return;
    }

    try {
      await closePersistentSession(session.sessionId);
      setSessions(prev => ({ ...prev, [platform]: null }));
    } catch (err) {
      console.error(`Failed to close ${platform} session:`, err);
    }
  }, []);

  const checkStatus = useCallback(async (
    platform: PersistentPlatform
  ): Promise<PersistentSessionStatus | null> => {
    const session = sessionsRef.current[platform];
    if (!session?.sessionId) {
      return null;
    }

    try {
      const status = await getPersistentSessionStatus(session.sessionId);
      if (status.status !== session.status) {
        setSessions(prev => ({
          ...prev,
          [platform]: { ...session, status: status.status as PersistentSession['status'] },
        }));
      }
      return status;
    } catch (err) {
      console.error(`Failed to check ${platform} status:`, err);
      return null;
    }
  }, []);

  const reinitSession = useCallback(async (platform: PersistentPlatform) => {
    await initSession(platform);
  }, [initSession]);

  return {
    sessions,
    loading,
    errors,
    refreshQR,
    refreshAllPersistentQR,
    closeSession,
    checkStatus,
    reinitSession,
  };
}
