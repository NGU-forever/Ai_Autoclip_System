// ========================================
// 交互式浏览器 Hook - 简化版
// 直接打开真实浏览器窗口，后端只记录 cookie
// ========================================

import { useState, useEffect, useCallback, useRef } from 'react';
import { http } from '../lib/http';

export type InteractivePlatform = 'douyin' | 'tencent' | 'xhs';

export type InteractiveSessionStatus = 
  | 'initializing' 
  | 'waiting_login' 
  | 'logged_in' 
  | 'creator_platform' 
  | 'closed';

export interface InteractiveSession {
  sessionId: string;
  platform: InteractivePlatform;
  status: InteractiveSessionStatus;
  userName?: string;
  accountId?: string;
  existingAccount?: {
    id: string;
    userName: string;
  };
}

export interface UseInteractiveBrowserReturn {
  session: InteractiveSession | null;
  isLoading: boolean;
  error: string | null;
  // Actions
  startBrowser: (platform: InteractivePlatform) => Promise<void>;
  closeBrowser: () => Promise<void>;
  // Status polling
  refreshStatus: () => Promise<void>;
}

export function useInteractiveBrowser(): UseInteractiveBrowserReturn {
  const [session, setSession] = useState<InteractiveSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const sessionRef = useRef<InteractiveSession | null>(null);
  
  // 保持 ref 同步
  useEffect(() => {
    sessionRef.current = session;
  }, [session]);
  
  // 启动浏览器
  const startBrowser = useCallback(async (platform: InteractivePlatform) => {
    setIsLoading(true);
    setError(null);
    
    try {
      // 先关闭现有会话
      if (sessionRef.current) {
        await closeBrowserInternal();
      }
      
      // 调用 API 启动浏览器
      const response = await http.post<any>(
        `/uploader/accounts/interactive/init?platform=${platform}`
      );
      
      const newSession: InteractiveSession = {
        sessionId: response.sessionId,
        platform: response.platform,
        status: response.status,
        userName: response.userName,
        accountId: response.accountId,
        existingAccount: response.existingAccount,
      };
      
      setSession(newSession);
      
    } catch (err) {
      const msg = err instanceof Error ? err.message : '启动浏览器失败';
      setError(msg);
      console.error('Start browser error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  // 刷新状态
  const refreshStatus = useCallback(async () => {
    if (!sessionRef.current?.sessionId) return;
    
    try {
      const response = await http.get<any>(
        `/uploader/accounts/interactive/${sessionRef.current.sessionId}/status`
      );
      
      setSession(prev => prev ? {
        ...prev,
        status: response.status,
        userName: response.userName,
        accountId: response.accountId,
      } : null);
      
    } catch (err) {
      console.error('Refresh status error:', err);
    }
  }, []);
  
  // 关闭浏览器（内部实现）
  const closeBrowserInternal = useCallback(async () => {
    if (sessionRef.current?.sessionId) {
      try {
        await http.post(`/uploader/accounts/interactive/${sessionRef.current.sessionId}/close`);
      } catch (e) {
        console.warn('Close browser error:', e);
      }
    }
    setSession(null);
  }, []);
  
  // 关闭浏览器（对外接口）
  const closeBrowser = useCallback(async () => {
    await closeBrowserInternal();
  }, [closeBrowserInternal]);
  
  // 状态轮询
  useEffect(() => {
    if (!session || session.status === 'closed') return;
    
    const interval = setInterval(() => {
      refreshStatus();
    }, 2000); // 每 2 秒轮询一次
    
    return () => clearInterval(interval);
  }, [session?.sessionId, session?.status, refreshStatus]);
  
  // 组件卸载时关闭浏览器
  useEffect(() => {
    return () => {
      closeBrowserInternal();
    };
  }, [closeBrowserInternal]);
  
  return {
    session,
    isLoading,
    error,
    startBrowser,
    closeBrowser,
    refreshStatus,
  };
}
