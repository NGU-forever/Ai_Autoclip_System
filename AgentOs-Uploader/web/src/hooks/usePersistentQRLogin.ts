// ========================================
// 分发页扫码：按需 qr-login（单任务浏览器，用完即关）
// Phase 3: 集成 WebSocket 实现实时状态推送，移除轮询
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
import { useWebSocketQR, type WebSocketQRMessage } from './useWebSocketQR';

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

function mapWebSocketStatusToModal(
  s: WebSocketQRMessage['status'] | undefined
): PersistentSession['status'] {
  return s || 'failed';
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

function toPersistentSessionStatusFromWebSocket(data: WebSocketQRMessage): PersistentSessionStatus {
  return {
    sessionId: data.sessionId,
    platform: data.platform,
    status: mapWebSocketStatusToModal(data.status),
    account: data.userName ? {
      id: data.sessionId,
      platform: data.platform as PersistentPlatform,
      userName: data.userName,
      cookieFile: '',
      status: 1,
    } : undefined,
    error: data.error,
  };
}

// ===== Hook =====

export interface UsePersistentQRLoginReturn {
  sessions: Record<PersistentPlatform, PersistentSession | null>;
  loading: Record<PersistentPlatform, boolean>;
  errors: Record<PersistentPlatform, string | null>;
  /** WebSocket 连接状态 */
  wsConnected: Record<PersistentPlatform, boolean>;
  /** 用户点击某平台扫码时调用：取消旧任务并启动新的 qr-login */
  requestQRLogin: (platform: PersistentPlatform) => Promise<void>;
  refreshQR: (platform: PersistentPlatform) => Promise<string | null>;
  refreshAllPersistentQR: () => Promise<boolean>;
  closeSession: (platform: PersistentPlatform) => void;
  /** 轮询检查状态（WebSocket 失败时的 fallback） */
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

const emptyWsConnected = (): Record<PersistentPlatform, boolean> => ({
  douyin: false,
  tencent: false,
  xhs: false,
});

export function usePersistentQRLogin(): UsePersistentQRLoginReturn {
  const [sessions, setSessions] = useState<Record<PersistentPlatform, PersistentSession | null>>(
    emptySessions
  );
  const [loading, setLoading] = useState<Record<PersistentPlatform, boolean>>(emptyLoading);
  const [errors, setErrors] = useState<Record<PersistentPlatform, string | null>>(emptyErrors);
  const [wsConnected, setWsConnected] = useState<Record<PersistentPlatform, boolean>>(emptyWsConnected);

  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  // 获取当前活跃的非成功会话 ID
  const getActiveSessionId = useCallback((platform: PersistentPlatform): string | null => {
    const session = sessionsRef.current[platform];
    if (session?.sessionId && session.status !== 'success') {
      return session.sessionId;
    }
    return null;
  }, []);

  // WebSocket 消息处理
  const handleWebSocketMessage = useCallback((platform: PersistentPlatform, data: WebSocketQRMessage) => {
    const currentSession = sessionsRef.current[platform];
    if (!currentSession) return;

    const newStatus = mapWebSocketStatusToModal(data.status);
    
    // 更新会话状态
    if (newStatus !== currentSession.status) {
      setSessions(prev => ({
        ...prev,
        [platform]: { ...currentSession, status: newStatus },
      }));
    }
  }, []);

  // 为每个平台创建 WebSocket 连接
  const douyinWs = useWebSocketQR({
    sessionId: getActiveSessionId('douyin'),
    onMessage: (data) => handleWebSocketMessage('douyin', data),
    onConnect: () => setWsConnected(prev => ({ ...prev, douyin: true })),
    onDisconnect: () => setWsConnected(prev => ({ ...prev, douyin: false })),
  });

  const tencentWs = useWebSocketQR({
    sessionId: getActiveSessionId('tencent'),
    onMessage: (data) => handleWebSocketMessage('tencent', data),
    onConnect: () => setWsConnected(prev => ({ ...prev, tencent: true })),
    onDisconnect: () => setWsConnected(prev => ({ ...prev, tencent: false })),
  });

  const xhsWs = useWebSocketQR({
    sessionId: getActiveSessionId('xhs'),
    onMessage: (data) => handleWebSocketMessage('xhs', data),
    onConnect: () => setWsConnected(prev => ({ ...prev, xhs: true })),
    onDisconnect: () => setWsConnected(prev => ({ ...prev, xhs: false })),
  });

  // WebSocket 连接映射
  const wsMap = {
    douyin: douyinWs,
    tencent: tencentWs,
    xhs: xhsWs,
  };

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

  // checkStatus 现在作为 WebSocket 失败时的 fallback
  const checkStatus = useCallback(
    async (platform: PersistentPlatform): Promise<PersistentSessionStatus | null> => {
      const session = sessionsRef.current[platform];
      if (!session?.sessionId) {
        return null;
      }

      // 如果 WebSocket 已连接，使用 WebSocket 的最新消息
      const ws = wsMap[platform];
      if (ws.isConnected && ws.lastMessage) {
        return toPersistentSessionStatusFromWebSocket(ws.lastMessage);
      }

      // WebSocket 未连接，使用 HTTP API 作为 fallback
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [douyinWs.isConnected, tencentWs.isConnected, xhsWs.isConnected, douyinWs.lastMessage, tencentWs.lastMessage, xhsWs.lastMessage]
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
    wsConnected,
    requestQRLogin,
    refreshQR,
    refreshAllPersistentQR,
    closeSession,
    checkStatus,
    reinitSession,
  };
}
