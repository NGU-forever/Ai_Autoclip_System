import { useLayoutEffect } from 'react';
import { startUploaderQiankun } from './uploaderQiankun';

/** 在 BrowserRouter 内执行一次，保证首屏若为 /distribute 时 #uploader-subapp 已提交再 start qiankun */
export function QiankunHostInit() {
  useLayoutEffect(() => {
    startUploaderQiankun();
  }, []);
  return null;
}
