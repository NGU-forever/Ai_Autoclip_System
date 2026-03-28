import { useEffect, useRef } from 'react';
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

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const injectedHead: HTMLElement[] = [];
    host.className = LEGACY_BODY_CLASS;
    host.innerHTML = shellBody;

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/style.css';
    document.head.appendChild(link);
    injectedHead.push(link);

    let cancelled = false;

    const run = async () => {
      try {
        injectedHead.push(await appendScript('https://cdn.jsdelivr.net/npm/marked/marked.min.js'));
        if (cancelled) return;
        injectedHead.push(await appendScript('https://cdn.jsdelivr.net/npm/dompurify/dist/purify.min.js'));
        if (cancelled) return;
        injectedHead.push(await appendScript('/static/pre-app-boot.js'));
        if (cancelled) return;
        injectedHead.push(await appendScript('/static/app.js', 'module'));
      } catch (e) {
        if (!cancelled) console.error(e);
      }
    };

    void run();

    return () => {
      cancelled = true;
      host.innerHTML = '';
      for (const el of injectedHead) {
        el.remove();
      }
    };
  }, []);

  return <div ref={hostRef} className="openstoryline-legacy-host" />;
}
