import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { renderWithQiankun, qiankunWindow } from 'vite-plugin-qiankun/dist/helper';
import './index.css';
import App from './App';

export type OpenStorylineQiankunProps = {
  container?: HTMLElement;
  /** 与基座 activeRule 一致，例如 /clip */
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

function render(props: OpenStorylineQiankunProps = {}) {
  const { container, routerBasename } = props;

  const w = window as unknown as { __OPENSTORYLINE_ROUTER_BASENAME__?: string };
  if (qiankunWindow.__POWERED_BY_QIANKUN__) {
    w.__OPENSTORYLINE_ROUTER_BASENAME__ = routerBasename ?? '/clip';
  } else {
    delete w.__OPENSTORYLINE_ROUTER_BASENAME__;
  }

  const mountEl = getMountEl(container);
  if (!mountEl) return;

  reactRoot?.unmount();
  reactRoot = createRoot(mountEl);
  reactRoot.render(
    <StrictMode>
      <BrowserRouter basename={w.__OPENSTORYLINE_ROUTER_BASENAME__ ?? '/'}>
        <App />
      </BrowserRouter>
    </StrictMode>,
  );
}

renderWithQiankun({
  async bootstrap() {},
  mount(props) {
    render(props as OpenStorylineQiankunProps);
  },
  unmount() {
    reactRoot?.unmount();
    reactRoot = null;
  },
  async update(props) {
    render(props as OpenStorylineQiankunProps);
  },
});

if (!qiankunWindow.__POWERED_BY_QIANKUN__) {
  render({});
}
