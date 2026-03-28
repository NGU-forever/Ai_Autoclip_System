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
    <div className="min-h-screen bg-bg flex flex-col">
      {inHost ? (
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
              <Clapperboard size={20} className="text-bg" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text tracking-tight">AI 智能剪辑</h1>
              <p className="text-xs text-muted">全自动化故事创作</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <a
              href={standalone7860}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 px-4 py-2 rounded-os-sm bg-surface-2 hover:bg-surface text-muted hover:text-text border border-border-os-weak text-sm transition-all"
            >
              <ExternalLink size={16} />
              新窗口打开（:7860）
            </a>
          </div>
        </header>
      ) : null}
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
