import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import qiankun from 'vite-plugin-qiankun';

export default defineConfig(({ mode }) => {
  const useDevMode = mode === 'development';
  return {
    base: mode === 'production' ? '/uploader-ui/' : '/',
    plugins: [react(), tailwindcss(), qiankun('uploader', { useDevMode })],
    server: {
      port: 5174,
      cors: true,
      origin: 'http://localhost:5174',
      proxy: {
        '/api': {
          target: 'http://localhost:8002',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
  };
});
