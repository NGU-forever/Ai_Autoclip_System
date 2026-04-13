import { useEffect, useRef, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import shellBody from '../legacy/shell-body.html?raw';

const LEGACY_BODY_CLASS = 'sidebar-collapsed devbar-collapsed';

function appendScript(src: string, type?: string): Promise<HTMLScriptElement> {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    if (type) s.type = type;
    s.async = false;
    s.onload = () => resolve(s);
    s.onerror = () => reject(new Error(`script load failed: ${src}`));
    document.head.appendChild(s);
  });
}

export function LegacyOpenStoryline() {
  const hostRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'loading' | 'error' | 'ready'>('loading');
  const [errorMsg, setErrorMsg] = useState<string>('');

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let cancelled = false;
    const injectedHead: HTMLElement[] = [];

    const loadAssets = async () => {
      try {
        setStatus('loading');
        
        // Setup host environment early
        host.className = LEGACY_BODY_CLASS;
        host.innerHTML = shellBody;

        // Load CSS and external libraries concurrently
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = '/static/style.css';
        document.head.appendChild(link);
        injectedHead.push(link);

        if (cancelled) return;

        // Parallelize first-level dependencies
        await Promise.all([
          appendScript('https://cdn.jsdelivr.net/npm/marked/marked.min.js').then(s => injectedHead.push(s)),
          appendScript('https://cdn.jsdelivr.net/npm/dompurify/dist/purify.min.js').then(s => injectedHead.push(s))
        ]);

        if (cancelled) return;

        // Sequence internal dependencies
        injectedHead.push(await appendScript('/static/pre-app-boot.js'));
        if (cancelled) return;
        injectedHead.push(await appendScript('/static/app.js', 'module'));
        
        if (!cancelled) {
          setStatus('ready');
        }
      } catch (e: any) {
        if (!cancelled) {
          console.error('[LegacyOpenStoryline] Boot failed:', e);
          setStatus('error');
          setErrorMsg(e.message || '加载核心资源失败，请检查网络连接或重试。');
        }
      }
    };

    void loadAssets();

    return () => {
      cancelled = true;
      if (host) {
        host.innerHTML = '';
      }
      for (const el of injectedHead) {
        el.remove();
      }
    };
  }, []); // Note: intentionally run once on mount

  const handleRetry = () => {
    setStatus('loading');
    setErrorMsg('');
    setTimeout(() => {
      window.location.reload();
    }, 100);
  };

  return (
    <>
      {status === 'loading' && (
        <div className="os-loading-wrapper">
          <div className="os-spinner" role="status" aria-label="正在加载剪辑系统"></div>
          <div className="os-loading-text">正在初始化核心环境...</div>
        </div>
      )}

      {status === 'error' && (
        <div className="os-error-wrapper">
          <AlertCircle size={48} className="os-error-icon" aria-hidden="true" />
          <h2 className="os-error-title">系统加载失败</h2>
          <p className="os-error-desc">{errorMsg}</p>
          <button className="os-retry-btn" onClick={handleRetry}>
            重新加载
          </button>
        </div>
      )}

      {/* 始终渲染 host(或用 display: none 隐藏) 以便 useEffects 能挂载 DOM，
          只有当 ready 时，才通过 CSS 控制它显示 */}
      <div 
        ref={hostRef} 
        className="openstoryline-legacy-host" 
        style={{ display: status === 'ready' ? 'block' : 'none' }}
      />
    </>
  );
}
