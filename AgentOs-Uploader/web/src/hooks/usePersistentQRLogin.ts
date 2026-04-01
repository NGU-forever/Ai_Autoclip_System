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
  persistentHeartbeat,
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

  // 获取当前活跃会话 ID（包括 success 状态，确保 WS 不会在成功处理完成前断开）
  const getActiveSessionId = useCallback((platform: PersistentPlatform): string | null => {
    const session = sessionsRef.current[platform];
    if (session?.sessionId) {
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
    if (newStatus !== currentSession.status || data.userName) {
      setSessions(prev => ({
        ...prev,
        [platform]: { 
          ...currentSession, 
          status: newStatus,
          message: data.message || currentSession.message,
          // 如果后端传了用户名，说明登录成功
          userName: data.userName || currentSession.userName
        },
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

  // HTTP 轮询 fallback：当 WebSocket 未连接时，通过 HTTP API 轮询状态
  // 这是关键的可靠性保障 —— Docker/nginx 可能不支持 WebSocket 升级
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

  // checkStatus: 登录成功时必须走 HTTP API 获取完整的 account 数据
  const checkStatus = useCallback(
    async (platform: PersistentPlatform): Promise<PersistentSessionStatus | null> => {
      const session = sessionsRef.current[platform];
      if (!session?.sessionId) {
        return null;
      }

      // 如果 WebSocket 已连接且状态不是 success，可以使用 WebSocket 的最新消息
      // 注意：success 时必须走 HTTP API，因为 WebSocket 消息不包含完整的 account 数据
      const ws = wsMap[platform];
      if (ws.isConnected && ws.lastMessage && ws.lastMessage.status !== 'success') {
        return toPersistentSessionStatusFromWebSocket(ws.lastMessage);
      }

      // 使用 HTTP API 获取完整状态（包括 account 信息）
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
