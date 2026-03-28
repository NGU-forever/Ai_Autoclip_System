import { useLayoutEffect } from 'react';
import { startUserMicroFrontends } from './microFrontendsQiankun';

/** 在 BrowserRouter 内执行一次，保证首屏子应用挂载 DOM 已提交再 start qiankun */
export function QiankunHostInit() {
  useLayoutEffect(() => {
    startUserMicroFrontends();
  }, []);
  return null;
}
