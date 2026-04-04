import { qiankunWindow } from 'vite-plugin-qiankun/dist/helper';

export type AuthBootstrapOptions = {
  /** 基座 qiankun props 注入 */
  accessToken?: string;
};

/** 开发模式：免认证（通过环境变量 VITE_DEV_MODE=true 启用） */
function isDevMode(): boolean {
  return import.meta.env.VITE_DEV_MODE === 'true' || import.meta.env.DEV === true;
}

/**
 * 鉴权引导：认证由 backend 服务统一处理。
 * 
 * 独立运行时：检查是否已登录（通过 backend 设置的 session cookie），
 * 未登录则跳转主站登录页。
 * 
 * qiankun 内无认证时不整页跳转（由基座 RequireAuth / beforeLoad 保证）。
 * 
 * 开发模式：设置 VITE_DEV_MODE=true 可跳过认证检查。
 */
export function bootstrapUploaderAuth(_options: AuthBootstrapOptions = {}): void {
  // 开发模式：跳过认证检查
  if (isDevMode()) {
    console.log('[Uploader] 开发模式：跳过认证检查');
    return;
  }

  // qiankun 环境下由基座处理认证，不在这里跳转
  if (qiankunWindow.__POWERED_BY_QIANKUN__) {
    return;
  }

  // 独立运行时的认证由 backend 统一处理
  // 如果未登录，backend 会返回 401，前端在 http.ts 中处理跳转
  // 这里不需要额外处理，因为所有请求都会经过 backend 代理
}
