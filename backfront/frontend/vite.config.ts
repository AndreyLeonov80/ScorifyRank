import { defineConfig } from 'vite';

declare const process: {
  env: Record<string, string | undefined>;
};

const backendTarget = process.env.X_FILES_API_BASE || 'http://127.0.0.1:8009';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 8008,
    strictPort: true,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 8008,
    strictPort: true,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
});
