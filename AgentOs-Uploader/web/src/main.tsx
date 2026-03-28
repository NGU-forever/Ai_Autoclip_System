import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { renderWithQiankun, qiankunWindow } from 'vite-plugin-qiankun/dist/helper';
import { ToastProvider } from './components/Toast';
import { bootstrapUploaderAuth } from './lib/authBootstrap';
import './index.css';
import App from './App';

export type UploaderQiankunProps = {
  container?: HTMLElement;
  accessToken?: string;
  /** 与基座 activeRule 一致，例如 /distribute */
  routerBasename?: string;
};

let reactRoot: Root | null = null;

function getMountEl(container?: HTMLElement): HTMLElement | null {
  if (container) {
    let inner = container.querySelector<HTMLElement>('#root');
    if (!inner) {
      inner = document.createElement('div');
      inner.id = 'root';
      container.appendChild(inner);
    }
    return inner;
  }
  return document.getElementById('root');
}

function render(props: UploaderQiankunProps = {}) {
  const { container, accessToken, routerBasename } = props;
  bootstrapUploaderAuth({ accessToken });

  const w = window as unknown as { __UPLOADER_ROUTER_BASENAME__?: string };
  if (qiankunWindow.__POWERED_BY_QIANKUN__) {
    w.__UPLOADER_ROUTER_BASENAME__ = routerBasename ?? '/distribute';
  } else {
    delete w.__UPLOADER_ROUTER_BASENAME__;
  }

  const mountEl = getMountEl(container);
  if (!mountEl) return;

  reactRoot?.unmount();
  reactRoot = createRoot(mountEl);
  reactRoot.render(
    <StrictMode>
      <BrowserRouter basename={w.__UPLOADER_ROUTER_BASENAME__ ?? '/'}>
        <ToastProvider>
          <App />
        </ToastProvider>
      </BrowserRouter>
    </StrictMode>,
  );
}

renderWithQiankun({
  async bootstrap() {},
  mount(props) {
    render(props as UploaderQiankunProps);
  },
  unmount() {
    reactRoot?.unmount();
    reactRoot = null;
  },
  async update(props) {
    render(props as UploaderQiankunProps);
  },
});

if (!qiankunWindow.__POWERED_BY_QIANKUN__) {
  render({});
}
