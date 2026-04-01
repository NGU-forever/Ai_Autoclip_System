import { useEffect, useRef, useCallback, useState } from 'react';

export type QRStatus = 'initializing' | 'ready' | 'scanning' | 'success' | 'failed' | 'expired';

export interface WebSocketQRMessage {
  sessionId: string;
  platform: string;
  status: QRStatus;
  userName?: string;
  error?: string;
  message?: string;
  timestamp?: number;
}

export interface UseWebSocketQROptions {
  sessionId: string | null;
  onMessage?: (data: WebSocketQRMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  pingInterval?: number;
}

export interface UseWebSocketQRReturn {
  isConnected: boolean;
  isConnecting: boolean;
  lastMessage: WebSocketQRMessage | null;
  error: Error | null;
  connect: () => void;
  disconnect: () => void;
  sendMessage: (message: string) => void;
}

/**
 * WebSocket Hook for QR Login real-time status
 * 
 * Features:
 * - Auto-reconnect with exponential backoff
 * - Ping/pong heartbeat
 * - Connection state management
 * - Automatic cleanup on unmount
 */
export function useWebSocketQR({
  sessionId,
  onMessage,
  onConnect,
  onDisconnect,
  onError,
  reconnectInterval = 3000,
  maxReconnectAttempts = 5,
  pingInterval = 30000,
}: UseWebSocketQROptions): UseWebSocketQRReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketQRMessage | null>(null);
  const [error, setError] = useState<Error | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isManualDisconnectRef = useRef(false);

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    isManualDisconnectRef.current = true;
    clearTimers();
    
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close(1000, 'Manual disconnect');
      }
      wsRef.current = null;
    }
    
    setIsConnected(false);
    setIsConnecting(false);
    onDisconnect?.();
  }, [clearTimers, onDisconnect]);

  const connect = useCallback(() => {
    if (!sessionId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    
    isManualDisconnectRef.current = false;
    setIsConnecting(true);
    setError(null);

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/admin/uploader/ws/qr-login/${sessionId}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log(`[WebSocket] Connected for session ${sessionId}`);
        setIsConnected(true);
        setIsConnecting(false);
        reconnectAttemptsRef.current = 0;
        onConnect?.();

        // Start ping interval
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, pingInterval);
      };

      ws.onmessage = (event) => {
        try {
          const data: WebSocketQRMessage = JSON.parse(event.data);
          setLastMessage(data);
          onMessage?.(data);
        } catch (err) {
          console.warn('[WebSocket] Failed to parse message:', event.data);
        }
      };

      ws.onerror = (event) => {
        console.error('[WebSocket] Error:', event);
        setError(new Error('WebSocket connection error'));
        onError?.(event);
      };

      ws.onclose = (event) => {
        console.log(`[WebSocket] Closed for session ${sessionId}, code: ${event.code}`);
        setIsConnected(false);
        setIsConnecting(false);
        wsRef.current = null;

        // Clear ping timer
        if (pingTimerRef.current) {
          clearInterval(pingTimerRef.current);
          pingTimerRef.current = null;
        }

        // Auto-reconnect if not manually disconnected and session exists
        if (!isManualDisconnectRef.current && sessionId) {
          if (reconnectAttemptsRef.current < maxReconnectAttempts) {
            reconnectAttemptsRef.current++;
            const delay = reconnectInterval * Math.min(reconnectAttemptsRef.current, 3);
            console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
            
            reconnectTimerRef.current = setTimeout(() => {
              connect();
            }, delay);
          } else {
            console.warn('[WebSocket] Max reconnect attempts reached');
            setError(new Error('Max reconnect attempts reached'));
          }
        }

        onDisconnect?.();
      };
    } catch (err) {
      console.error('[WebSocket] Failed to create connection:', err);
      setIsConnecting(false);
      setError(err instanceof Error ? err : new Error('Failed to create WebSocket'));
    }
  }, [sessionId, onMessage, onConnect, onDisconnect, onError, reconnectInterval, maxReconnectAttempts, pingInterval]);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    } else {
      console.warn('[WebSocket] Cannot send message, not connected');
    }
  }, []);

  // Auto-connect when sessionId changes
  useEffect(() => {
    if (sessionId) {
      reconnectAttemptsRef.current = 0;
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [sessionId, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimers();
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
      }
    };
  }, [clearTimers]);

  return {
    isConnected,
    isConnecting,
    lastMessage,
    error,
    connect,
    disconnect,
    sendMessage,
  };
}

export default useWebSocketQR;
