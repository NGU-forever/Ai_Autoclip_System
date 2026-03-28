import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '../../context/ThemeContext.tsx'
import { ToastProvider } from '../../components/Toast.tsx'
import '../../index.css'
import App from './App.tsx'
import { QiankunHostInit } from './QiankunHostInit.tsx'

// 部署版本校验逻辑：如果发现版本更新（每次构建生成新的时间戳），则强制清理本地缓存状态并要求重新登录。
const VERSION_KEY = 'app_version_users';
const currentVersion = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev';
const storedVersion = localStorage.getItem(VERSION_KEY);

if (storedVersion !== currentVersion) {
  console.log(`[Version Check] New version detected (${currentVersion}), clearing auth state...`);
  localStorage.removeItem('access_token');
  localStorage.removeItem('current_user');
  localStorage.setItem(VERSION_KEY, currentVersion);
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <QiankunHostInit />
          <App />
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
