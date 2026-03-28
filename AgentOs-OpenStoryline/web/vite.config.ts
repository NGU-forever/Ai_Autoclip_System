import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import qiankun from 'vite-plugin-qiankun';

export default defineConfig(({ mode }) => {
  const useDevMode = mode === 'development';
  return {
    base: mode === 'production' ? '/openstoryline-ui/' : '/',
    plugins: [react(), qiankun('openstoryline', { useDevMode })],
    server: {
      port: 5175,
      cors: true,
      origin: 'http://localhost:5175',
      fs: { allow: ['..'] },
      proxy: {
        '/api': { target: 'http://localhost:7860', changeOrigin: true },
        '/ws': { target: 'ws://localhost:7860', ws: true, changeOrigin: true },
        '/static': { target: 'http://localhost:7860', changeOrigin: true },
        '/node_map': { target: 'http://localhost:7860', changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
  };
});
