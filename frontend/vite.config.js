import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// `__dirname` does not exist in an ESM config (package.json sets type: module);
// it only appears to work because Vite transpiles the config before running it.
const rootDir = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(rootDir, 'src') },
  },
  build: {
    rollupOptions: {
      output: {
        // Recharts is by far the heaviest dependency and is only needed on the
        // dashboards, so it is split out rather than shipped in the entry chunk.
        manualChunks: {
          charts: ['recharts'],
          vendor: ['react', 'react-dom', 'react-router-dom', 'axios'],
        },
      },
    },
  },
  server: {
    port: 5173,
    // The backend is called through this proxy in development, so the browser
    // makes same-origin requests and CORS never enters the picture.
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
