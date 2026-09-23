import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'html-rewrite-react',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          // Serve app.html at root to preserve standalone index.html intact
          if (req.url === '/' || req.url === '') {
            req.url = '/app.html';
          }
          next();
        });
      },
    },
  ],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'app.html'),
      },
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
