// ========================================
// Video Distributor - 视频分发中心
// ========================================

import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Video,
  Users,
  Send,
  RefreshCw,
  LogOut,
  Plus,
  Trash2,
  X,
  Upload,
  Check,
  AlertCircle,
  FileVideo,
  Hash,
  Type,
  Image as ImageIcon,
  ChevronDown,
  ExternalLink,
  Play,
  Pause,
  Clock,
  HardDrive,
  QrCode,
  Smartphone,
  ScanLine,
  CheckCircle2,
  XCircle,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { clearAuth, redirectToMainLogin } from '../lib/http';
import { useToast } from '../components/Toast';
import {
  useVideos,
  useAccounts,
  usePublish,
  uploadCover,
  uploadVideo,
  VideoItem,
  Account,
  PublishParams,
  UploaderCookieInvalidError,
} from '../hooks/useUploader';
import { usePersistentQRLogin } from '../hooks/usePersistentQRLogin';
import { useInteractiveBrowser } from '../hooks/useInteractiveBrowser';

const MAIN_APP_ORIGIN = (import.meta.env.VITE_MAIN_APP_ORIGIN || 'http://localhost').replace(/\/$/, '');

type QRPersistPlatform = 'douyin' | 'tencent' | 'xhs';



// ===== Constants =====

const PLATFORMS = [
  { id: 'douyin', name: '抖音', color: '#000000', icon: '▶' },
  { id: 'tencent', name: '视频号', color: '#07C160', icon: '✓' },
  { id: 'xhs', name: '小红书', color: '#FF2442', icon: '📕' },
];

const TENCENT_CATEGORIES = [
  '生活',
  '美食',
  '旅行',
  '知识',
  '搞笑',
  '游戏',
  '音乐',
  '影视',
  '时尚',
  '体育',
  '萌宠',
  '汽车',
  '科技',
  '母婴',
  '政务',
];

// 格式化日期时间为本地格式（用于datetime-local输入）
const formatDateTimeLocal = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

// 生成短标题（6-16字符）
const generateShortTitle = (title: string): string => {
  // 移除非字母数字字符，保留中文、英文、数字
  const cleaned = title.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, '');
  if (cleaned.length >= 6 && cleaned.length <= 16) {
    return cleaned;
  } else if (cleaned.length < 6) {
    return cleaned.padEnd(6, ' ');
  } else {
    return cleaned.slice(0, 16);
  }
};

// ===== Components =====

// Header Component
const Header: React.FC<{ onLogout: () => void; onRefresh: () => void; refreshing: boolean }> = ({
  onLogout,
  onRefresh,
  refreshing,
}) => (
  <header className="h-[64px] os-glass border-b border-border-os-weak flex items-center justify-between px-6 sticky top-0 z-40">
    <div className="flex items-center gap-4">
      <a
        href="/"
        className="flex items-center gap-2 text-muted hover:text-text transition-colors"
      >
        <div className="w-8 h-8 rounded-os-sm bg-surface-2 flex items-center justify-center border border-border-os-weak">
          <Sparkles size={16} />
        </div>
        <span className="text-sm">返回工作台</span>
      </a>
      <div className="h-6 w-px bg-border-os-weak" />
      <div className="w-10 h-10 rounded-os-sm bg-primary flex items-center justify-center shadow-os-soft">
        <Send size={20} className="text-bg" />
      </div>
      <div>
        <h1 className="text-lg font-bold text-text tracking-tight">视频分发中心</h1>
        <p className="text-xs text-muted">一键发布到多个平台</p>
      </div>
    </div>
    <div className="flex items-center gap-3">
      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="flex items-center gap-2 px-4 py-2 rounded-os-sm bg-surface-2 hover:bg-surface text-muted hover:text-text border border-border-os-weak text-sm transition-all disabled:opacity-50"
      >
        <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
        刷新列表
      </button>
      <button
        onClick={onLogout}
        className="flex items-center gap-2 px-4 py-2 rounded-os-sm bg-red-500/10 hover:bg-red-500/20 text-red-500 text-sm transition-all"
      >
        <LogOut size={16} />
        退出登录
      </button>
    </div>
  </header>
);

// Video List Component
const VideoList: React.FC<{
  videos: VideoItem[];
  selectedVideo: VideoItem | null;
  onSelect: (video: VideoItem) => void;
  loading: boolean;
  onUpload: (file: File) => void;
  uploading: boolean;
}> = ({ videos, selectedVideo, onSelect, loading, onUpload, uploading }) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '未知时间';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type.startsWith('video/')) {
        onUpload(file);
      } else {
        // Not a video file might be handled inside the parent, but checking here
        onUpload(file); // Parent will handle the toast or error if it fails
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onUpload(e.target.files[0]);
    }
    e.target.value = '';
  };

  return (
    <div 
      className={`h-full flex flex-col os-card overflow-hidden transition-colors border-2 ${
        isDragging ? 'border-primary bg-primary/5' : 'border-transparent'
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="p-4 border-b border-border-os-weak flex items-center justify-between">
        <div className="flex items-center gap-2 text-text font-semibold">
          <FileVideo size={18} className="text-primary" />
          视频库
          <span className="text-xs font-normal text-muted ml-1">{videos.length} 个视频</span>
        </div>
        <div>
          <input 
            type="file" 
            accept="video/*" 
            className="hidden" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            disabled={uploading}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-os-sm bg-surface-2 hover:bg-surface text-primary border border-border-os-weak text-xs font-medium transition-all shadow-sm disabled:opacity-50"
          >
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            上传视频
          </button>
        </div>
      </div>
      
      {/* 拖拽提示层 */}
      {isDragging && (
        <div className="absolute inset-0 z-10 bg-bg/80 backdrop-blur-sm flex flex-col items-center justify-center border-2 border-dashed border-primary rounded-os-md m-2">
          <Upload size={48} className="text-primary mb-4" />
          <p className="text-lg font-medium text-text">松开鼠标上传视频</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2 space-y-1 relative">
        {loading || uploading ? (
          <div className="flex flex-col items-center justify-center h-48 text-muted mt-8">
            <Loader2 size={32} className="text-primary animate-spin mb-3" />
            <span className="text-sm">{uploading ? '正在上传...' : '加载中...'}</span>
          </div>
        ) : videos.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted">
            <Video size={32} className="mb-2 opacity-30" />
            <span className="text-sm">暂无视频</span>
          </div>
        ) : (
          videos.map((video) => (
            <motion.button
              key={video.id}
              onClick={() => onSelect(video)}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              className={`w-full p-3 rounded-os-sm text-left transition-all ${
                selectedVideo?.id === video.id
                  ? 'bg-primary/10 border border-primary/30'
                  : 'bg-surface-2 hover:bg-surface border border-transparent'
              }`}
            >
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-os-sm flex items-center justify-center flex-shrink-0 ${
                  selectedVideo?.id === video.id ? 'bg-primary' : 'bg-muted/10'
                }`}>
                  <Play size={16} className="text-bg ml-0.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text font-medium truncate">{video.filename}</p>
                  <p className="text-xs text-muted mt-1">{formatDate(video.createdAt)}</p>
                  {video.sizeMb && (
                    <p className="text-xs text-muted mt-0.5 flex items-center gap-1">
                      <HardDrive size={10} />
                      {video.sizeMb.toFixed(1)} MB
                    </p>
                  )}
                </div>
                {selectedVideo?.id === video.id && (
                  <Check size={16} className="text-primary flex-shrink-0" />
                )}
              </div>
            </motion.button>
          ))
        )}
      </div>
    </div>
  );
};

// Video Preview Component
const VideoPreview: React.FC<{ video: VideoItem | null }> = ({ video }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  if (!video) {
    return (
      <div className="h-full flex flex-col items-center justify-center os-card text-muted">
        <Video size={48} className="mb-4 opacity-20" />
        <p className="text-sm">选择一个视频进行预览</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col os-card overflow-hidden">
      <div className="p-4 border-b border-border-os-weak">
        <div className="flex items-center gap-2 text-text font-semibold">
          <Play size={18} className="text-primary" />
          视频预览
        </div>
      </div>
      <div className="flex-1 p-4 flex items-center justify-center bg-black/5">
        <div className="relative w-full max-w-lg aspect-video bg-black rounded-os-md shadow-os overflow-hidden group">
          <video
            ref={videoRef}
            src={`/api/admin/uploader/video-stream/${video.id}`}
            className="w-full h-full object-contain"
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            controls
          />
        </div>
      </div>
      <div className="p-4 border-t border-border-os-weak">
        <p className="text-sm text-muted">
          文件名: <span className="text-text font-medium">{video.filename}</span>
        </p>
        <p className="text-xs text-muted mt-1 truncate">
          路径: {video.filePath}
        </p>
      </div>
    </div>
  );
};

// QR Login Modal Component（按需 qr-login，单任务浏览器）
const QRLoginModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  platform: QRPersistPlatform | null;
  onSuccess: (account: Account) => void;
  /** 登录成功但接口未带 account 时刷新列表（防御性） */
  onAccountsRefresh?: () => void | Promise<void>;
  /** 关闭扫码弹窗时取消后端任务，释放浏览器 */
  onDismissQRLogin?: (platform: QRPersistPlatform) => void | Promise<void>;
  persistentSession?: { sessionId: string; qrUrl: string; status: string } | null;
  initError?: string | null;
  platformInitLoading?: boolean;
  onReinitSession?: (platform: QRPersistPlatform) => Promise<void>;
  onRefreshQR?: (platform: QRPersistPlatform) => Promise<string | null>;
  onCheckStatus?: (platform: QRPersistPlatform) => Promise<{
    sessionId: string;
    platform: string;
    status: string;
    account?: Account;
    error?: string;
  } | null>;
}> = ({
  isOpen,
  onClose,
  platform,
  onSuccess,
  onAccountsRefresh,
  onDismissQRLogin,
  persistentSession,
  initError = null,
  platformInitLoading = false,
  onReinitSession,
  onRefreshQR,
  onCheckStatus,
}) => {
  const [localStatus, setLocalStatus] = useState<'idle' | 'loading' | 'waiting' | 'scanned' | 'success' | 'failed'>('idle');
  const [qrImageUrl, setQrImageUrl] = useState<string | null>(null);
  /** 图片已解码并显示，避免 <img> 加载前白底空框闪烁 */
  const [qrImageLoaded, setQrImageLoaded] = useState(false);
  const [qrLoadError, setQrLoadError] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  // Phase 3: 移除 intervalRef（不再使用轮询）
  const qrRetryCountRef = useRef(0);
  /** 用户点击「刷新二维码」后，等图片 onLoad 再提示成功，避免接口返回快但图未就绪时误显「已刷新」 */
  const refreshSuccessPendingRef = useRef(false);
  const refreshSuccessTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { showToast } = useToast();

  const clearRefreshSuccessTimer = () => {
    if (refreshSuccessTimerRef.current) {
      clearTimeout(refreshSuccessTimerRef.current);
      refreshSuccessTimerRef.current = null;
    }
  };

  const platformName = platform === 'douyin' ? '抖音' : platform === 'tencent' ? '视频号' : platform === 'xhs' ? '小红书' : '';
  const platformColor = platform === 'douyin' ? '#000000' : platform === 'tencent' ? '#07C160' : '#FF2442';

  const showInitFailure = Boolean(platform && !persistentSession?.sessionId && initError);
  const showSpinnerNoQr = Boolean(
    platform &&
      !persistentSession?.sessionId &&
      !initError &&
      platformInitLoading,
  );
  const showWaitingPlaceholder = Boolean(
    platform &&
      !persistentSession?.sessionId &&
      !initError &&
      !platformInitLoading,
  );

  useEffect(() => {
    if (!isOpen || !platform) return;

    if (persistentSession?.sessionId) {
      setQrImageUrl(`${persistentSession.qrUrl}?t=${Date.now()}`);
      setQrLoadError(false);
      qrRetryCountRef.current = 0;

      if (persistentSession.status === 'initializing') {
        setLocalStatus('waiting');
      } else if (persistentSession.status === 'ready') {
        setLocalStatus('waiting');
      } else if (persistentSession.status === 'scanning') {
        setLocalStatus('scanned');
      } else if (persistentSession.status === 'success') {
        setLocalStatus('success');
      } else if (persistentSession.status === 'failed' || persistentSession.status === 'expired') {
        setLocalStatus('failed');
      }
    } else {
      setQrImageUrl(null);
      setLocalStatus(initError ? 'idle' : 'loading');
    }
  }, [isOpen, platform, persistentSession, initError]);

  useEffect(() => {
    if (!isOpen) {
      clearRefreshSuccessTimer();
      refreshSuccessPendingRef.current = false;
    }
  }, [isOpen]);

  useLayoutEffect(() => {
    setQrImageLoaded(false);
  }, [qrImageUrl]);

  // Phase 3: 使用 WebSocket 实时推送，移除轮询
  // 监听 persistentSession.status 变化，同步到 localStatus
  useEffect(() => {
    if (!persistentSession?.sessionId) return;
    
    // 当状态从外部（WebSocket）更新时，同步本地状态
    if (persistentSession.status === 'success' && localStatus !== 'success') {
      setLocalStatus('success');
      // 登录成功，触发回调
      pollStatusAndHandleSuccess();
    } else if (persistentSession.status === 'scanning' && localStatus !== 'scanned') {
      setLocalStatus('scanned');
    } else if (
      (persistentSession.status === 'failed' || persistentSession.status === 'expired') &&
      localStatus !== 'failed'
    ) {
      setLocalStatus('failed');
    } else if (persistentSession.status === 'ready' && localStatus === 'loading') {
      setLocalStatus('waiting');
    }
  }, [persistentSession?.status, persistentSession?.sessionId]);

  // 登录成功时获取完整状态（包括账号信息）
  const pollStatusAndHandleSuccess = async () => {
    if (!platform || !onCheckStatus) return;

    // 短暂延迟，确保后端已完成 cookie 保存和账号注册
    await new Promise(resolve => setTimeout(resolve, 800));

    const MAX_RETRIES = 3;
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      try {
        const status = await onCheckStatus(platform);
        if (status?.status === 'success') {
          if (status.account && status.account.id && status.account.cookieFile) {
            // 后端返回了完整的 account，先添加到本地
            onSuccess(status.account);
          }
          // 始终从后端刷新账号列表（后端已在 _handle_login_success 中自动注册）
          await onAccountsRefresh?.();
          handleClose();
          return;
        }
        // 如果状态还不是 success，等一下再重试
        if (attempt < MAX_RETRIES - 1) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      } catch (error) {
        console.warn('Failed to get success status (attempt ' + (attempt + 1) + '):', error);
        if (attempt < MAX_RETRIES - 1) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
    }
    // 兜底：重试耗尽也刷新一次账号列表
    await onAccountsRefresh?.();
  };

  // 保留 pollStatus 作为手动检查（WebSocket fallback）
  const pollStatus = async () => {
    if (!platform || !onCheckStatus) return;
    try {
      const status = await onCheckStatus(platform);
      if (status) {
        if (status.status === 'success') {
          setLocalStatus('success');
          if (status.account) {
            onSuccess(status.account);
          } else {
            await onAccountsRefresh?.();
            handleClose();
          }
        } else if (status.status === 'failed' || status.status === 'expired') {
          setLocalStatus('failed');
        } else if (status.status === 'scanning') {
          setLocalStatus('scanned');
        }
      }
    } catch (error) {
      // Silently handle polling errors
    }
  };

  const handleClose = () => {
    // Phase 3: 移除 interval 清理（不再使用轮询）
    clearRefreshSuccessTimer();
    refreshSuccessPendingRef.current = false;
    setLocalStatus('idle');
    setQrImageUrl(null);
    setQrImageLoaded(false);
    setQrLoadError(false);
    setIsRefreshing(false);
    qrRetryCountRef.current = 0;
    if (platform) {
      void onDismissQRLogin?.(platform);
    }
    onClose();
  };

  const handleRefresh = async () => {
    if (!platform) return;
    if (!onRefreshQR) return;

    const hadQrBefore = qrImageUrl != null;
    setIsRefreshing(true);
    setQrLoadError(false);
    qrRetryCountRef.current = 0;
    if (localStatus !== 'scanned' && localStatus !== 'success') {
      setLocalStatus('waiting');
    }

    try {
      const newQrUrl = await onRefreshQR(platform);

      if (newQrUrl) {
        setQrImageUrl(newQrUrl);
        setLocalStatus('waiting');
        refreshSuccessPendingRef.current = true;
        clearRefreshSuccessTimer();
        refreshSuccessTimerRef.current = setTimeout(() => {
          refreshSuccessTimerRef.current = null;
          if (refreshSuccessPendingRef.current) {
            refreshSuccessPendingRef.current = false;
            showToast('warning', '二维码加载较慢，请稍候或再次点击刷新');
          }
        }, 12000);
      } else {
        showToast('error', '刷新失败，请重试');
        setLocalStatus(hadQrBefore ? 'waiting' : 'failed');
      }
    } catch {
      showToast('error', '刷新失败，请重试');
      setLocalStatus(hadQrBefore ? 'waiting' : 'failed');
    } finally {
      setIsRefreshing(false);
    }
  };

  if (!isOpen || !platform) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-text/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
        onClick={handleClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className="os-card bg-bg w-full max-w-sm overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="p-5 border-b border-border-os-weak flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className="w-8 h-8 rounded-os-sm flex items-center justify-center text-bg font-bold text-sm"
                style={{ backgroundColor: platformColor }}
              >
                {platform === 'douyin' ? '▶' : platform === 'tencent' ? '✓' : '📕'}
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text">扫码登录 {platformName}</h3>
                <p className="text-xs text-muted">请使用手机 APP 扫描二维码</p>
              </div>
            </div>
            <button onClick={handleClose} className="p-1 rounded-os-sm hover:bg-surface-2 text-muted">
              <X size={20} />
            </button>
          </div>

          {/* QR Code Area */}
          <div className="p-6">
            <div className="relative w-48 h-48 mx-auto bg-white rounded-os-md border border-border-os-weak overflow-hidden flex items-center justify-center">
              {showInitFailure ? (
                <div className="flex flex-col items-center gap-3 px-2 text-center">
                  <AlertCircle size={40} className="text-amber-500 shrink-0" />
                  <p className="text-sm text-slate-600">{platformName} 会话初始化失败</p>
                  <p className="text-xs text-muted break-all max-w-full">{initError}</p>
                  <button
                    type="button"
                    onClick={() => platform && onReinitSession?.(platform)}
                    disabled={platformInitLoading || !onReinitSession}
                    className="mt-1 flex items-center justify-center gap-2 px-4 py-2 bg-primary text-bg rounded-os-sm text-sm font-medium disabled:opacity-50"
                  >
                    {platformInitLoading ? <Loader2 size={16} className="animate-spin" /> : null}
                    重新初始化
                  </button>
                </div>
              ) : showSpinnerNoQr ? (
                <div className="flex flex-col items-center gap-3">
                  <Loader2 size={32} className="text-primary animate-spin" />
                  <span className="text-sm text-slate-600">正在建立扫码会话…</span>
                </div>
              ) : showWaitingPlaceholder ? (
                <div className="flex flex-col items-center gap-3">
                  <QrCode size={40} className="text-slate-400" />
                  <span className="text-sm text-slate-600">等待生成二维码</span>
                </div>
              ) : localStatus === 'failed' || qrLoadError ? (
                <div className="flex flex-col items-center gap-3">
                  <XCircle size={40} className="text-red-500" />
                  <span className="text-sm text-slate-600">
                    {qrLoadError ? '二维码加载失败' : '二维码已失效'}
                  </span>
                </div>
              ) : qrImageUrl && !qrLoadError ? (
                <>
                  <img
                    key={qrImageUrl}
                    src={qrImageUrl}
                    alt=""
                    decoding="async"
                    className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-200 ${
                      !qrImageLoaded
                        ? 'opacity-0'
                        : localStatus === 'scanned' || localStatus === 'success'
                          ? 'opacity-10'
                          : 'opacity-100'
                    }`}
                    onLoad={() => {
                      setQrImageLoaded(true);
                      if (refreshSuccessPendingRef.current) {
                        refreshSuccessPendingRef.current = false;
                        clearRefreshSuccessTimer();
                        showToast('success', '二维码已刷新');
                      }
                    }}
                    onError={() => {
                      if (qrRetryCountRef.current < 5) {
                        qrRetryCountRef.current++;
                        setTimeout(() => {
                          setQrImageUrl(prev => (prev ? `${prev.split('?')[0]}?t=${Date.now()}` : null));
                        }, 2000);
                      } else {
                        if (refreshSuccessPendingRef.current) {
                          refreshSuccessPendingRef.current = false;
                          clearRefreshSuccessTimer();
                          showToast('error', '二维码加载失败，请重试');
                        }
                        setQrLoadError(true);
                      }
                    }}
                  />
                  {!qrImageLoaded && !isRefreshing && (
                    <div className="absolute inset-0 z-[5] flex flex-col items-center justify-center gap-2 bg-white">
                      <Loader2 size={28} className="text-primary animate-spin" />
                      <span className="text-xs text-slate-600 px-2 text-center">正在加载二维码…</span>
                    </div>
                  )}
                  {(persistentSession?.status === 'initializing' || isRefreshing) && (
                    <div className="absolute inset-0 bg-white/75 flex flex-col items-center justify-center gap-2 z-10">
                      <Loader2 size={28} className="text-primary animate-spin" />
                      <span className="text-xs text-slate-600 px-2 text-center">正在刷新二维码…</span>
                    </div>
                  )}
                  {(localStatus === 'scanned' || localStatus === 'success') && (
                    <div className="absolute inset-0 flex items-center justify-center z-[11]">
                      <div className="flex flex-col items-center gap-2">
                        <CheckCircle2 size={40} className="text-green-500" />
                        <span className="text-sm font-medium text-green-600">
                          {localStatus === 'success' ? '登录成功' : '已扫描，确认中...'}
                        </span>
                      </div>
                    </div>
                  )}
                </>
              ) : localStatus === 'loading' ? (
                <div className="flex flex-col items-center gap-3">
                  <Loader2 size={32} className="text-primary animate-spin" />
                  <span className="text-sm text-slate-600">正在生成二维码...</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3">
                  <QrCode size={40} className="text-slate-400" />
                  <span className="text-sm text-slate-600">等待生成二维码</span>
                </div>
              )}
            </div>

            {/* Status Info */}
            <div className="mt-6 text-center">
              {localStatus === 'waiting' && (
                <div className="flex items-center justify-center gap-2 text-muted">
                  <ScanLine size={16} className="animate-pulse" />
                  <span className="text-sm">请打开手机 {platformName} APP 扫描二维码</span>
                </div>
              )}
              {localStatus === 'scanned' && (
                <div className="flex items-center justify-center gap-2 text-primary">
                  <Smartphone size={16} />
                  <span className="text-sm">请在手机上确认登录</span>
                </div>
              )}
              {localStatus === 'failed' && (
                <div className="flex items-center justify-center gap-2 text-red-500">
                  <AlertCircle size={16} />
                  <span className="text-sm">二维码已过期，请刷新重试</span>
                </div>
              )}
            </div>

            {/* Refresh Button */}
            {persistentSession?.sessionId &&
              (localStatus === 'failed' || localStatus === 'waiting' || qrLoadError) &&
              !isRefreshing && (
              <button
                onClick={() => {
                  setQrLoadError(false);
                  qrRetryCountRef.current = 0;
                  handleRefresh();
                }}
                disabled={persistentSession?.status === 'initializing'}
                className="w-full mt-4 flex items-center justify-center gap-2 px-4 py-2.5 bg-surface-2 hover:bg-surface border border-border-os-weak rounded-os-sm text-sm text-text transition-colors disabled:opacity-50"
              >
                <RefreshCw size={16} />
                刷新二维码
              </button>
            )}
          </div>

          {/* Footer */}
          <div className="px-5 py-4 bg-surface-2 border-t border-border-os-weak">
            <div className="flex items-center gap-2 text-xs text-muted">
              <AlertCircle size={12} />
              <span>二维码有效期为 5 分钟，超时请刷新</span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

// Interactive Browser Login Component (noVNC 版)
const InteractiveBrowserLogin: React.FC<{
  onAccountAdded: () => void;
}> = ({ onAccountAdded }) => {
  const { showToast } = useToast();
  
  const {
    session,
    isLoading,
    error,
    startBrowser,
    closeBrowser,
  } = useInteractiveBrowser();

  // 监听登录成功
  useEffect(() => {
    if (session?.status === 'logged_in' && session.accountId) {
      showToast('success', `登录成功：${session.userName || '新账号'}`);
      onAccountAdded();
    }
  }, [session?.status, session?.accountId, session?.userName, onAccountAdded, showToast]);

  // 获取状态文本
  const getStatusText = () => {
    if (!session) return '请选择平台启动浏览器';
    switch (session.status) {
      case 'initializing': return '正在启动浏览器...';
      case 'waiting_login': return '请在下方浏览器中完成登录';
      case 'logged_in': return '登录成功！';
      case 'creator_platform': return session.existingAccount 
        ? `已打开 ${session.existingAccount.userName} 的创作者平台` 
        : '已打开创作者平台';
      case 'closed': return '浏览器已关闭';
      default: return '未知状态';
    }
  };

  // 获取状态颜色
  const getStatusColor = () => {
    if (!session) return 'text-muted';
    switch (session.status) {
      case 'initializing': return 'text-amber-500';
      case 'waiting_login': return 'text-blue-500';
      case 'logged_in': return 'text-green-500';
      case 'creator_platform': return 'text-green-600';
      case 'closed': return 'text-red-500';
      default: return 'text-muted';
    }
  };

  // 如果浏览器未启动，显示平台选择
  if (!session) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-4"
      >
        <p className="text-sm text-muted text-center">
          选择平台启动浏览器，在下方窗口中完成登录
        </p>
        <div className="grid grid-cols-3 gap-4">
          <button
            onClick={() => startBrowser('douyin')}
            disabled={isLoading}
            className="flex flex-col items-center gap-3 p-6 bg-surface-2 hover:bg-surface border border-border-os-weak hover:border-primary/50 rounded-os-md transition-all group shadow-sm hover:shadow-os-soft disabled:opacity-50"
          >
            <div className="w-14 h-14 rounded-os-sm bg-black flex items-center justify-center text-white text-xl group-hover:scale-110 transition-transform shadow-lg">
              ▶
            </div>
            <div className="text-center">
              <p className="text-text font-medium">抖音</p>
              <p className="text-xs text-muted mt-1">浏览器登录</p>
            </div>
          </button>

          <button
            onClick={() => startBrowser('tencent')}
            disabled={isLoading}
            className="flex flex-col items-center gap-3 p-6 bg-surface-2 hover:bg-surface border border-border-os-weak hover:border-primary/50 rounded-os-md transition-all group shadow-sm hover:shadow-os-soft disabled:opacity-50"
          >
            <div className="w-14 h-14 rounded-os-sm bg-[#07C160] flex items-center justify-center text-white text-xl group-hover:scale-110 transition-transform shadow-lg">
              ✓
            </div>
            <div className="text-center">
              <p className="text-text font-medium">视频号</p>
              <p className="text-xs text-muted mt-1">浏览器登录</p>
            </div>
          </button>

          <button
            onClick={() => startBrowser('xhs')}
            disabled={isLoading}
            className="flex flex-col items-center gap-3 p-6 bg-surface-2 hover:bg-surface border border-border-os-weak hover:border-primary/50 rounded-os-md transition-all group shadow-sm hover:shadow-os-soft disabled:opacity-50"
          >
            <div className="w-14 h-14 rounded-os-sm bg-[#FF2442] flex items-center justify-center text-white text-xl group-hover:scale-110 transition-transform shadow-lg">
              📕
            </div>
            <div className="text-center">
              <p className="text-text font-medium">小红书</p>
              <p className="text-xs text-muted mt-1">浏览器登录</p>
            </div>
          </button>
        </div>
        
        {isLoading && (
          <div className="flex items-center justify-center gap-2 text-muted py-4">
            <Loader2 size={20} className="animate-spin text-primary" />
            <span>正在启动浏览器...</span>
          </div>
        )}
        
        {error && (
          <div className="flex items-center gap-2 text-red-500 text-sm justify-center">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}
        
        <div className="flex items-start gap-2 text-xs text-muted bg-surface-2 p-3 rounded-os-sm">
          <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
          <div className="space-y-1">
            <p>使用说明：</p>
            <ul className="list-disc list-inside space-y-0.5">
              <li>点击平台按钮启动浏览器</li>
              <li>在下方窗口中完成登录</li>
              <li>登录成功后账号自动保存</li>
              <li>点击"关闭浏览器"结束会话（30分钟自动关闭）</li>
            </ul>
          </div>
        </div>
      </motion.div>
    );
  }

  // 浏览器已启动，显示 noVNC 全屏嵌入
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex flex-col bg-bg"
    >
      {/* 顶部状态栏 */}
      <div className="h-14 bg-surface-2 border-b border-border-os-weak flex items-center justify-between px-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div 
            className="w-8 h-8 rounded-os-sm flex items-center justify-center text-white text-sm font-bold"
            style={{ 
              backgroundColor: 
                session.platform === 'douyin' ? '#000' : 
                session.platform === 'tencent' ? '#07C160' : '#FF2442' 
            }}
          >
            {session.platform === 'douyin' ? '▶' : 
             session.platform === 'tencent' ? '✓' : '📕'}
          </div>
          <div>
            <p className="text-sm font-medium text-text">
              {session.platform === 'douyin' ? '抖音' : 
               session.platform === 'tencent' ? '视频号' : '小红书'}
            </p>
            <p className={`text-xs ${getStatusColor()}`}>{getStatusText()}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* 状态图标 */}
          {session.status === 'initializing' && (
            <Loader2 size={18} className="animate-spin text-amber-500" />
          )}
          {session.status === 'waiting_login' && (
            <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          )}
          {session.status === 'logged_in' && (
            <CheckCircle2 size={18} className="text-green-500" />
          )}
          {session.status === 'creator_platform' && (
            <CheckCircle2 size={18} className="text-green-600" />
          )}
          
          {/* 账号信息 */}
          {session.userName && (
            <div className="flex items-center gap-1.5 text-sm text-muted bg-bg px-2 py-1 rounded-os-sm">
              <Check size={12} className="text-green-500" />
              <span>{session.userName}</span>
            </div>
          )}
          
          {/* 关闭按钮 */}
          <button
            onClick={closeBrowser}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/30 rounded-os-sm text-sm font-medium transition-colors"
          >
            <X size={14} />
            关闭浏览器
          </button>
        </div>
      </div>

      {/* noVNC 嵌入区域 */}
      <div className="flex-1 relative">
        <iframe
          src={`${window.location.protocol}//${window.location.hostname}:6080/vnc.html?autoconnect=true&resize=scale&quality=9&compression=2&shared=true`}
          className="w-full h-full border-0"
          title="Browser"
          allow="fullscreen"
        />
      </div>
    </motion.div>
  );
};

// Account Manager Modal
const AccountManager: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  accounts: Account[];
  onAdd: (platform: string, userName: string, cookieFile: File) => Promise<Account | void>;
  onDelete: (id: string) => Promise<void>;
  onAddByQR: (account: Account) => void | Promise<void>;
  loading: boolean;
  persistentSessions?: {
    douyin: { sessionId: string; qrUrl: string; status: string } | null;
    tencent: { sessionId: string; qrUrl: string; status: string } | null;
    xhs: { sessionId: string; qrUrl: string; status: string } | null;
  };
  persistentErrors?: Record<QRPersistPlatform, string | null>;
  persistentSessionLoading?: Record<QRPersistPlatform, boolean>;
  onReinitPersistentSession?: (platform: QRPersistPlatform) => Promise<void>;
  onRefreshQR?: (platform: QRPersistPlatform) => Promise<string | null>;
  onCheckStatus?: (platform: QRPersistPlatform) => Promise<{
    sessionId: string;
    platform: string;
    status: string;
    account?: Account;
    error?: string;
  } | null>;
  onAccountsRefresh?: () => void | Promise<void>;
  onRequestQRLogin?: (platform: QRPersistPlatform) => Promise<void>;
  onDismissQRLogin?: (platform: QRPersistPlatform) => void | Promise<void>;
}> = ({
  isOpen,
  onClose,
  accounts,
  onAdd,
  onDelete,
  onAddByQR,
  loading,
  persistentSessions,
  persistentErrors,
  persistentSessionLoading,
  onReinitPersistentSession,
  onRefreshQR,
  onCheckStatus,
  onAccountsRefresh,
  onRequestQRLogin,
  onDismissQRLogin,
}) => {
  const [activeTab, setActiveTab] = useState<'qr' | 'browser'>('qr');
  const [showQRLogin, setShowQRLogin] = useState(false);
  const [qrPlatform, setQrPlatform] = useState<QRPersistPlatform | null>(null);

  useEffect(() => {
    if (!isOpen && qrPlatform) {
      void onDismissQRLogin?.(qrPlatform);
      setShowQRLogin(false);
      setQrPlatform(null);
    }
  }, [isOpen, qrPlatform, onDismissQRLogin]);
  
  // Manual form state
  const [platform, setPlatform] = useState<'douyin' | 'tencent' | 'xhs'>('douyin');
  const [userName, setUserName] = useState('');
  const [cookieFile, setCookieFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userName.trim() || !cookieFile) return;
    
    setIsSubmitting(true);
    try {
      await onAdd(platform, userName, cookieFile);
      setUserName('');
      setCookieFile(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenQRLogin = async (platformType: QRPersistPlatform) => {
    setQrPlatform(platformType);
    setShowQRLogin(true);
    await onRequestQRLogin?.(platformType);
  };

  const handleQRSuccess = (account: Account) => {
    const p = qrPlatform;
    onAddByQR(account);
    if (p) {
      void onDismissQRLogin?.(p);
    }
    setShowQRLogin(false);
    setQrPlatform(null);
  };

  const handleCloseQRLogin = () => {
    setShowQRLogin(false);
    setQrPlatform(null);
  };

  if (!isOpen) return null;

  return (
    <>
      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-text/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className="os-card bg-bg w-full max-w-lg overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-border-os-weak flex items-center justify-between">
              <h3 className="text-lg font-semibold text-text flex items-center gap-2">
                <Users size={20} className="text-primary" />
                账号管理
              </h3>
              <button onClick={onClose} className="p-1 rounded-os-sm hover:bg-surface-2 text-muted">
                <X size={20} />
              </button>
            </div>

            <div className="p-5">
              {/* Tabs */}
              <div className="flex gap-2 mb-6 p-1 bg-surface-2 rounded-os-sm border border-border-os-weak">
                <button
                  onClick={() => setActiveTab('qr')}
                  className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-os-sm text-sm font-medium transition-all ${
                    activeTab === 'qr'
                      ? 'bg-primary text-bg shadow-os-soft'
                      : 'text-muted hover:text-text'
                  }`}
                >
                  <QrCode size={16} />
                  扫码添加（推荐）
                </button>
                <button
                  onClick={() => setActiveTab('browser')}
                  className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-os-sm text-sm font-medium transition-all ${
                    activeTab === 'browser'
                      ? 'bg-primary text-bg shadow-os-soft'
                      : 'text-muted hover:text-text'
                  }`}
                >
                  <ExternalLink size={16} />
                  浏览器登录
                </button>
              </div>

              {/* QR Tab Content */}
              {activeTab === 'qr' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4 mb-6"
                >
                  <p className="text-sm text-muted text-center">
                    选择平台，使用手机扫码快速添加账号
                  </p>
                  <div className="grid grid-cols-3 gap-4">
                    {/* Douyin QR Button */}
                    <button
                      onClick={() => handleOpenQRLogin('douyin')}
                      className="flex flex-col items-center gap-3 p-6 bg-surface-2 hover:bg-surface border border-border-os-weak hover:border-primary/50 rounded-os-md transition-all group shadow-sm hover:shadow-os-soft"
                    >
                      <div className="w-14 h-14 rounded-os-sm bg-black flex items-center justify-center text-white text-xl group-hover:scale-110 transition-transform shadow-lg">
                        ▶
                      </div>
                      <div className="text-center">
                        <p className="text-text font-medium">抖音</p>
                        <p className="text-xs text-muted mt-1">扫码快速登录</p>
                      </div>
                    </button>

                    {/* Tencent QR Button */}
                    <button
                      onClick={() => handleOpenQRLogin('tencent')}
                      className="flex flex-col items-center gap-3 p-6 bg-surface-2 hover:bg-surface border border-border-os-weak hover:border-primary/50 rounded-os-md transition-all group shadow-sm hover:shadow-os-soft"
                    >
                      <div className="w-14 h-14 rounded-os-sm bg-[#07C160] flex items-center justify-center text-white text-xl group-hover:scale-110 transition-transform shadow-lg">
                        ✓
                      </div>
                      <div className="text-center">
                        <p className="text-text font-medium">视频号</p>
                        <p className="text-xs text-muted mt-1">扫码快速登录</p>
                      </div>
                    </button>

                    {/* XHS QR Button */}
                    <button
                      onClick={() => handleOpenQRLogin('xhs')}
                      className="flex flex-col items-center gap-3 p-6 bg-surface-2 hover:bg-surface border border-border-os-weak hover:border-primary/50 rounded-os-md transition-all group shadow-sm hover:shadow-os-soft"
                    >
                      <div className="w-14 h-14 rounded-os-sm bg-[#FF2442] flex items-center justify-center text-white text-xl group-hover:scale-110 transition-transform shadow-lg">
                        📕
                      </div>
                      <div className="text-center">
                        <p className="text-text font-medium">小红书</p>
                        <p className="text-xs text-muted mt-1">扫码快速登录</p>
                      </div>
                    </button>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted justify-center">
                    <CheckCircle2 size={12} className="text-green-500" />
                    <span>无需手动上传 cookie，扫码即可自动完成登录</span>
                  </div>
                </motion.div>
              )}

              {/* Browser Login Tab Content */}
              {activeTab === 'browser' && (
                <InteractiveBrowserLogin 
                  onAccountAdded={() => {
                    onAccountsRefresh?.();
                    setActiveTab('qr');
                  }}
                />
              )}

              {/* Account List */}
              <div className="border-t border-border-os-weak pt-4">
                <h4 className="text-sm font-medium text-text mb-3">已配置账号 ({accounts.length})</h4>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {accounts.length === 0 ? (
                    <p className="text-sm text-muted text-center py-4">暂无账号，请先添加</p>
                  ) : (
                    accounts.map((account) => (
                      <div
                        key={account.id}
                        className="flex items-center justify-between p-3 bg-surface-2 rounded-os-sm border border-border-os-weak"
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className="w-2.5 h-2.5 rounded-full"
                            style={{ 
                              backgroundColor: account.platform === 'douyin' 
                                ? '#000' 
                                : account.platform === 'tencent' 
                                  ? '#07C160' 
                                  : '#FF2442' 
                            }}
                          />
                          <div>
                            <p className="text-sm text-text font-medium">{account.userName}</p>
                            <p className="text-xs text-muted">
                              {account.platform === 'douyin' ? '抖音' : account.platform === 'tencent' ? '视频号' : '小红书'}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => onDelete(account.id)}
                          disabled={loading}
                          className="p-1.5 rounded-os-sm hover:bg-red-500/10 text-muted hover:text-red-500 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </AnimatePresence>

      {/* QR Login Modal */}
      <QRLoginModal
        isOpen={showQRLogin}
        onClose={handleCloseQRLogin}
        platform={qrPlatform}
        onSuccess={handleQRSuccess}
        onAccountsRefresh={onAccountsRefresh}
        onDismissQRLogin={onDismissQRLogin}
        persistentSession={
          qrPlatform && persistentSessions ? persistentSessions[qrPlatform] : null
        }
        initError={
          qrPlatform && persistentErrors ? persistentErrors[qrPlatform] ?? null : null
        }
        platformInitLoading={
          qrPlatform && persistentSessionLoading
            ? Boolean(persistentSessionLoading[qrPlatform])
            : false
        }
        onReinitSession={onReinitPersistentSession}
        onRefreshQR={onRefreshQR}
        onCheckStatus={onCheckStatus}
      />
    </>
  );
};

// Publish Form Component
const PublishForm: React.FC<{
  selectedVideo: VideoItem | null;
  accounts: Account[];
  onPublish: (params: PublishParams[]) => Promise<void>;
  publishing: boolean;
  onManageAccounts: () => void;
}> = ({ selectedVideo, accounts, onPublish, publishing, onManageAccounts }) => {
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState<Record<string, string>>({});
  
  // 视频号配置
  const [tencentCategory, setTencentCategory] = useState('生活');
  const [isDraft, setIsDraft] = useState(false);
  const [tencentShortTitle, setTencentShortTitle] = useState('');
  const [declareOriginal, setDeclareOriginal] = useState(false);
  
  // 抖音配置
  const [douyinThumbnail, setDouyinThumbnail] = useState<File | null>(null);
  const [douyinThumbnailPath, setDouyinThumbnailPath] = useState('');
  const [productLink, setProductLink] = useState('');
  const [productTitle, setProductTitle] = useState('');
  
  // 小红书配置
  const [xhsDesc, setXhsDesc] = useState('');
  const [xhsIsPrivate, setXhsIsPrivate] = useState(false);
  const [xhsCover, setXhsCover] = useState<File | null>(null);
  const [xhsCoverPath, setXhsCoverPath] = useState('');
  
  // 通用：定时发布
  const [enableSchedule, setEnableSchedule] = useState(false);
  const [scheduleTime, setScheduleTime] = useState(() => {
    const now = new Date();
    now.setHours(now.getHours() + 1);
    return formatDateTimeLocal(now);
  });
  
  const { showToast } = useToast();

  const douyinAccounts = accounts.filter((a) => a.platform === 'douyin');
  const tencentAccounts = accounts.filter((a) => a.platform === 'tencent');
  const xhsAccounts = accounts.filter((a) => a.platform === 'xhs');

  const getPlatformAccounts = (platformId: string) => {
    switch (platformId) {
      case 'douyin': return douyinAccounts;
      case 'tencent': return tencentAccounts;
      case 'xhs': return xhsAccounts;
      default: return [];
    }
  };

  const getPlatformName = (platformId: string) => {
    switch (platformId) {
      case 'douyin': return '抖音';
      case 'tencent': return '视频号';
      case 'xhs': return '小红书';
      default: return platformId;
    }
  };

  const handlePlatformToggle = (platformId: string) => {
    setSelectedPlatforms((prev) => {
      const newState = { ...prev };
      if (newState[platformId]) {
        delete newState[platformId];
      } else {
        const platformAccounts = getPlatformAccounts(platformId);
        if (platformAccounts.length > 0) {
          newState[platformId] = platformAccounts[0].id;
        } else {
          showToast('error', `请先添加${getPlatformName(platformId)}账号`);
          return prev;
        }
      }
      return newState;
    });
  };

  const handleAccountChange = (platformId: string, accountId: string) => {
    setSelectedPlatforms((prev) => ({
      ...prev,
      [platformId]: accountId,
    }));
  };

  const handleSubmit = async () => {
    if (!selectedVideo) {
      showToast('error', '请先选择一个视频');
      return;
    }
    if (!title.trim()) {
      showToast('error', '请输入视频标题');
      return;
    }
    if (Object.keys(selectedPlatforms).length === 0) {
      showToast('error', '请至少选择一个发布平台');
      return;
    }

    const tagList = tags
      .split(/[\s,#]+/)
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

    // 上传封面（如果有）
    let uploadedDouyinThumbnail = '';
    let uploadedXhsCover = '';
    
    try {
      if (selectedPlatforms['douyin'] && douyinThumbnail) {
        const result = await uploadCover(douyinThumbnail);
        uploadedDouyinThumbnail = result.filePath;
      }
      if (selectedPlatforms['xhs'] && xhsCover) {
        const result = await uploadCover(xhsCover);
        uploadedXhsCover = result.filePath;
      }
    } catch (err) {
      showToast('error', '封面上传失败');
      return;
    }

    // 构建定时发布时间
    const publishDate = enableSchedule ? new Date(scheduleTime).toISOString() : undefined;

    const publishTasks: PublishParams[] = Object.entries(selectedPlatforms).map(([platform, accountId]) => {
      const baseParams: PublishParams = {
        platform: platform as 'douyin' | 'tencent' | 'xhs',
        accountId,
        videoId: selectedVideo.id,
        title: title.trim(),
        tags: tagList,
        publishDate,
      };

      if (platform === 'douyin') {
        return {
          ...baseParams,
          thumbnailPath: uploadedDouyinThumbnail || undefined,
          productLink: productLink || undefined,
          productTitle: productTitle || undefined,
        };
      }

      if (platform === 'tencent') {
        return {
          ...baseParams,
          category: tencentCategory,
          isDraft,
          shortTitle: tencentShortTitle || generateShortTitle(title),
          declareOriginal,
        };
      }

      if (platform === 'xhs') {
        return {
          ...baseParams,
          desc: xhsDesc || title.trim(),
          isPrivate: xhsIsPrivate,
          coverPath: uploadedXhsCover || undefined,
        };
      }

      return baseParams;
    });

    await onPublish(publishTasks);
  };

  const parseTags = (input: string) => {
    const parsed = input
      .split(/[\s,#]+/)
      .map((t) => t.trim())
      .filter((t) => t.length > 0);
    return parsed;
  };

  return (
    <div className="h-full flex flex-col os-card overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-border-os-weak">
        <div className="flex items-center gap-2 text-text font-semibold">
          <Send size={18} className="text-primary" />
          发布配置
        </div>
      </div>

      {/* Form Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Platform Selection */}
        <div>
          <label className="block text-sm text-muted mb-3">选择发布平台</label>
          <div className="space-y-2">
            {PLATFORMS.map((platform) => (
              <div
                key={platform.id}
                className={`p-3 rounded-os-sm border transition-all ${
                  selectedPlatforms[platform.id]
                    ? 'bg-primary/5 border-primary/30'
                    : 'bg-surface-2 border-border-os-weak hover:border-primary/50 shadow-sm'
                }`}
              >
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={!!selectedPlatforms[platform.id]}
                    onChange={() => handlePlatformToggle(platform.id)}
                    className="w-4 h-4 rounded border-border-os-weak bg-bg text-primary focus:ring-primary focus:ring-offset-0 transition-colors"
                  />
                  <div
                    className="w-8 h-8 rounded-os-sm flex items-center justify-center text-bg font-bold text-sm shadow-sm"
                    style={{ backgroundColor: platform.color }}
                  >
                    {platform.icon}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-text font-medium">{platform.name}</p>
                  </div>
                </div>

                {/* Account Selection */}
                {selectedPlatforms[platform.id] && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    className="mt-3 pl-7"
                  >
                    <select
                      value={selectedPlatforms[platform.id]}
                      onChange={(e) => handleAccountChange(platform.id, e.target.value)}
                      className="w-full bg-bg border border-border-os-weak rounded-os-sm px-3 py-2 text-text text-sm focus:outline-none focus:border-primary transition-colors"
                    >
                      {getPlatformAccounts(platform.id).map((acc) => (
                        <option key={acc.id} value={acc.id}>
                          {acc.userName}
                        </option>
                      ))}
                    </select>

                    {/* Douyin-specific options */}
                    {platform.id === 'douyin' && (
                      <div className="mt-3 space-y-3">
                        {/* 封面上传 */}
                        <div>
                          <label className="text-xs text-muted block mb-1">视频封面</label>
                          <label className="flex items-center gap-2 px-3 py-2 bg-bg border border-border-os-weak border-dashed rounded-os-sm cursor-pointer hover:bg-surface-2 transition-colors">
                            <ImageIcon size={16} className="text-primary" />
                            <span className="text-sm text-muted truncate">
                              {douyinThumbnail ? douyinThumbnail.name : '点击上传封面图片'}
                            </span>
                            <input
                              type="file"
                              accept="image/*"
                              onChange={(e) => setDouyinThumbnail(e.target.files?.[0] || null)}
                              className="hidden"
                            />
                          </label>
                        </div>
                        
                        {/* 商品链接 */}
                        <div>
                          <label className="text-xs text-muted block mb-1">商品链接（可选）</label>
                          <input
                            type="text"
                            value={productLink}
                            onChange={(e) => setProductLink(e.target.value)}
                            placeholder="https://..."
                            className="w-full bg-bg border border-border-os-weak rounded-os-sm px-3 py-2 text-text text-sm placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
                          />
                        </div>
                        {productLink && (
                          <div>
                            <label className="text-xs text-muted block mb-1">商品短标题</label>
                            <input
                              type="text"
                              value={productTitle}
                              onChange={(e) => setProductTitle(e.target.value.slice(0, 10))}
                              placeholder="10字以内"
                              className="w-full bg-bg border border-border-os-weak rounded-os-sm px-3 py-2 text-text text-sm placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
                            />
                          </div>
                        )}
                      </div>
                    )}

                    {/* Tencent-specific options */}
                    {platform.id === 'tencent' && (
                      <div className="mt-3 space-y-3">
                        <div>
                          <label className="text-xs text-muted block mb-1">视频分类</label>
                          <select
                            value={tencentCategory}
                            onChange={(e) => setTencentCategory(e.target.value)}
                            className="w-full bg-bg border border-border-os-weak rounded-os-sm px-3 py-2 text-text text-sm focus:outline-none focus:border-primary transition-colors"
                          >
                            {TENCENT_CATEGORIES.map((cat) => (
                              <option key={cat} value={cat}>
                                {cat}
                              </option>
                            ))}
                          </select>
                        </div>
                        
                        {/* 短标题 */}
                        <div>
                          <label className="text-xs text-muted block mb-1">短标题（6-16字符）</label>
                          <input
                            type="text"
                            value={tencentShortTitle}
                            onChange={(e) => setTencentShortTitle(e.target.value.slice(0, 16))}
                            placeholder={generateShortTitle(title)}
                            className="w-full bg-bg border border-border-os-weak rounded-os-sm px-3 py-2 text-text text-sm placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
                          />
                        </div>
                        
                        {/* 原创声明 */}
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={declareOriginal}
                            onChange={(e) => setDeclareOriginal(e.target.checked)}
                            className="w-4 h-4 rounded border-border-os-weak bg-bg text-primary focus:ring-primary transition-colors"
                          />
                          <span className="text-sm text-muted">声明原创</span>
                        </label>
                        
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={isDraft}
                            onChange={(e) => setIsDraft(e.target.checked)}
                            className="w-4 h-4 rounded border-border-os-weak bg-bg text-primary focus:ring-primary transition-colors"
                          />
                          <span className="text-sm text-muted">保存为草稿</span>
                        </label>
                      </div>
                    )}

                    {/* XHS-specific options */}
                    {platform.id === 'xhs' && (
                      <div className="mt-3 space-y-3">
                        {/* 封面上传 */}
                        <div>
                          <label className="text-xs text-muted block mb-1">视频封面</label>
                          <label className="flex items-center gap-2 px-3 py-2 bg-bg border border-border-os-weak border-dashed rounded-os-sm cursor-pointer hover:bg-surface-2 transition-colors">
                            <ImageIcon size={16} className="text-primary" />
                            <span className="text-sm text-muted truncate">
                              {xhsCover ? xhsCover.name : '点击上传封面图片'}
                            </span>
                            <input
                              type="file"
                              accept="image/*"
                              onChange={(e) => setXhsCover(e.target.files?.[0] || null)}
                              className="hidden"
                            />
                          </label>
                        </div>
                        
                        <div>
                          <label className="text-xs text-muted block mb-1">详细描述</label>
                          <textarea
                            value={xhsDesc}
                            onChange={(e) => setXhsDesc(e.target.value)}
                            placeholder="输入详细描述内容（可选，默认使用标题）"
                            rows={3}
                            className="w-full bg-bg border border-border-os-weak rounded-os-sm px-3 py-2 text-text text-sm placeholder:text-muted focus:outline-none focus:border-primary transition-colors resize-none"
                          />
                        </div>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={xhsIsPrivate}
                            onChange={(e) => setXhsIsPrivate(e.target.checked)}
                            className="w-4 h-4 rounded border-border-os-weak bg-bg text-primary focus:ring-primary transition-colors"
                          />
                          <span className="text-sm text-muted">私密发布（仅自己可见）</span>
                        </label>
                      </div>
                    )}
                  </motion.div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Title Input */}
        <div>
          <label className="flex items-center gap-2 text-sm text-muted mb-2">
            <Type size={14} />
            视频标题
            <span className="text-xs text-muted ml-auto">{title.length}/100</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value.slice(0, 100))}
            placeholder="输入吸引人的标题..."
            className="w-full bg-surface-2 border border-border-os-weak rounded-os-sm px-3 py-2.5 text-text text-sm placeholder:text-muted focus:outline-none focus:border-primary transition-all"
          />
        </div>

        {/* Tags Input */}
        <div>
          <label className="flex items-center gap-2 text-sm text-muted mb-2">
            <Hash size={14} />
            话题标签
            <span className="text-xs text-muted ml-auto">用空格或#分隔</span>
          </label>
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="#热门话题 #推荐"
            className="w-full bg-surface-2 border border-border-os-weak rounded-os-sm px-3 py-2.5 text-text text-sm placeholder:text-muted focus:outline-none focus:border-primary transition-all"
          />
          {tags && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {parseTags(tags).map((tag, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full border border-primary/20"
                >
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Schedule Publish */}
        <div className="p-4 bg-surface-2 rounded-os-sm border border-border-os-weak">
          <label className="flex items-center gap-2 cursor-pointer mb-3">
            <input
              type="checkbox"
              checked={enableSchedule}
              onChange={(e) => setEnableSchedule(e.target.checked)}
              className="w-4 h-4 rounded border-border-os-weak bg-bg text-primary focus:ring-primary transition-colors"
            />
            <Clock size={16} className="text-muted" />
            <span className="text-sm text-text font-medium">定时发布</span>
          </label>
          
          {enableSchedule && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              className="pl-6"
            >
              <input
                type="datetime-local"
                value={scheduleTime}
                onChange={(e) => setScheduleTime(e.target.value)}
                min={formatDateTimeLocal(new Date())}
                className="w-full bg-bg border border-border-os-weak rounded-os-sm px-3 py-2 text-text text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <p className="text-xs text-muted mt-1">
                选择未来的时间，视频将在指定时间自动发布
              </p>
            </motion.div>
          )}
        </div>

        {/* Account Management Button */}
        <button
          onClick={onManageAccounts}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-surface-2 hover:bg-surface border border-border-os-weak rounded-os-sm text-sm text-muted hover:text-text transition-all shadow-sm"
        >
          <Users size={16} />
          管理发布账号 ({accounts.length})
        </button>
      </div>

      {/* Submit Button */}
      <div className="p-4 border-t border-border-os-weak">
        <button
          onClick={handleSubmit}
          disabled={publishing || !selectedVideo}
          className="w-full h-12 flex items-center justify-center gap-2 px-4 bg-primary hover:bg-primary-dark text-bg rounded-os-sm font-semibold shadow-os-soft disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
        >
          {publishing ? (
            <>
              <RefreshCw size={18} className="animate-spin" />
              提交中...
            </>
          ) : (
            <>
              <Send size={18} />
              一键发布
              {Object.keys(selectedPlatforms).length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-bg/20 rounded text-xs">
                  {Object.keys(selectedPlatforms).length}
                </span>
              )}
            </>
          )}
        </button>
        <p className="text-[10px] text-muted text-center mt-2">
          发布后将在后台自动完成浏览器上传
        </p>
      </div>
    </div>
  );
};

// ===== Main Component =====

export const VideoDistributor: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { showToast } = useToast();
  
  const { videos, loading: videosLoading, fetchVideos } = useVideos();
  const {
    accounts,
    loading: accountsLoading,
    fetchAccounts,
    addNewAccount,
    addNewAccountByQR,
    removeAccount,
  } = useAccounts();
  const { loading: publishing, submitPublish } = usePublish();
  
  const {
    sessions: persistentSessions,
    errors: persistentErrors,
    loading: persistentSessionLoading,
    requestQRLogin,
    refreshQR,
    checkStatus,
    reinitSession,
    closeSession,
  } = usePersistentQRLogin();
  
  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  const [showAccountManager, setShowAccountManager] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [uploadingVideo, setUploadingVideo] = useState(false);

  // Initial data load
  useEffect(() => {
    fetchVideos();
    fetchAccounts();
  }, [fetchVideos, fetchAccounts]);

  // Handle video param from URL
  useEffect(() => {
    const videoId = searchParams.get('video');
    if (videoId && videos.length > 0) {
      const video = videos.find((v) => v.id === videoId);
      if (video) {
        setSelectedVideo(video);
      }
    }
  }, [searchParams, videos]);

  const handleUploadVideo = useCallback(async (file: File) => {
    // 基础文件类型校验
    if (!file.type.startsWith('video/')) {
      showToast('error', '请选择视频文件 (.mp4, .mov, etc)');
      return;
    }

    setUploadingVideo(true);
    try {
      showToast('info', '开始上传视频...');
      const result = await uploadVideo(file);
      showToast('success', '视频上传成功');
      await fetchVideos(); // 刷新列表
      setSelectedVideo(result); // 自动选中刚上传的视频
    } catch (err) {
      showToast('error', err instanceof Error ? err.message : '上传视频失败');
    } finally {
      setUploadingVideo(false);
    }
  }, [fetchVideos, showToast]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([fetchVideos(), fetchAccounts()]);
      showToast('success', '列表已刷新');
    } finally {
      setRefreshing(false);
    }
  }, [fetchVideos, fetchAccounts, showToast]);

  const handleLogout = useCallback(() => {
    clearAuth();
    redirectToMainLogin();
  }, []);

  const handlePublish = useCallback(
    async (params: PublishParams[]) => {
      try {
        const results = await Promise.all(params.map((p) => submitPublish(p)));
        const successCount = results.filter((r) => r?.success).length;

        if (successCount === params.length) {
          showToast('success', `已成功提交 ${successCount} 个发布任务`);
        } else {
          showToast('warning', `提交完成：${successCount}/${params.length} 成功`);
        }
      } catch (e) {
        if (e instanceof UploaderCookieInvalidError) {
          showToast('error', e.message);
          setShowAccountManager(true);
          return;
        }
        throw e;
      }
    },
    [submitPublish, showToast],
  );

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <Header onLogout={handleLogout} onRefresh={handleRefresh} refreshing={refreshing} />
      
      <main className="flex-1 p-6 overflow-hidden">
        <div className="h-full grid grid-cols-12 gap-6">
          {/* Left: Video List */}
          <div className="col-span-3 h-full">
            <VideoList
              videos={videos}
              selectedVideo={selectedVideo}
              onSelect={setSelectedVideo}
              loading={videosLoading}
              onUpload={handleUploadVideo}
              uploading={uploadingVideo}
            />
          </div>

          {/* Center: Video Preview */}
          <div className="col-span-5 h-full">
            <VideoPreview video={selectedVideo} />
          </div>

          {/* Right: Publish Form */}
          <div className="col-span-4 h-full">
            <PublishForm
              selectedVideo={selectedVideo}
              accounts={accounts}
              onPublish={handlePublish}
              publishing={publishing}
              onManageAccounts={() => setShowAccountManager(true)}
            />
          </div>
        </div>
      </main>

      {/* Account Manager Modal */}
      <AccountManager
        isOpen={showAccountManager}
        onClose={() => setShowAccountManager(false)}
        accounts={accounts}
        onAdd={addNewAccount}
        onDelete={removeAccount}
        onAddByQR={async (account) => {
          addNewAccountByQR(account);
          await fetchAccounts();
        }}
        loading={accountsLoading}
        persistentSessions={persistentSessions}
        persistentErrors={persistentErrors}
        persistentSessionLoading={persistentSessionLoading}
        onReinitPersistentSession={reinitSession}
        onRefreshQR={refreshQR}
        onCheckStatus={checkStatus}
        onAccountsRefresh={fetchAccounts}
        onRequestQRLogin={requestQRLogin}
        onDismissQRLogin={(p) => void closeSession(p)}
      />
    </div>
  );
};

export default VideoDistributor;
