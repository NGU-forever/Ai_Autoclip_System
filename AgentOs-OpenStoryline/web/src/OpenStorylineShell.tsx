import type { ReactNode } from 'react';
import { Sparkles, Clapperboard, ExternalLink } from 'lucide-react';
import { qiankunWindow } from 'vite-plugin-qiankun/dist/helper';

/**
 * 嵌入主站（qiankun）时的顶栏：在子应用内实现，基座只提供 #openstoryline-subapp 容器。
 */
export function OpenStorylineShell({ children }: { children: ReactNode }) {
  const inHost = qiankunWindow.__POWERED_BY_QIANKUN__;
  const standalone7860 = `${window.location.protocol}//${window.location.hostname}:7860`;

  return (
    <div className="os-layout">
      {inHost ? (
        <header className="os-header" role="banner">
          <div className="os-header-left">
            <a
              href="/"
              className="os-back-link"
              aria-label="返回工作台"
            >
              <div className="os-icon-box" aria-hidden="true">
                <Sparkles size={16} />
              </div>
              <span>返回工作台</span>
            </a>
            <div className="os-divider" aria-hidden="true" />
            <div className="os-primary-icon" aria-hidden="true">
              <Clapperboard size={20} />
            </div>
            <div className="os-title-block">
              <h1>AI 智能剪辑</h1>
              <p>全自动化故事创作</p>
            </div>
          </div>
          <div className="os-header-right">
            <a
              href={standalone7860}
              target="_blank"
              rel="noreferrer"
              className="os-external-btn"
              aria-label="在新窗口中打开7860端口"
            >
              <ExternalLink size={16} aria-hidden="true" />
              <span>新窗口打开（:7860）</span>
            </a>
          </div>
        </header>
      ) : null}
      <main className="os-main" role="main">
        {children}
      </main>
    </div>
  );
}
