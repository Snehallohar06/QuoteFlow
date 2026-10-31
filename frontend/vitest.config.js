import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// `__dirname` does not exist in an ESM config (package.json sets type: module);
// it only appears to work because Vite transpiles the config before running it.
const rootDir = path.dirname(fileURLToPath(import.meta.url))

/**
 * The smoke suite mounts real pages against the real backend.
 *
 * jsdom's document URL is set to the dev server's origin, so the relative
 * `/api/v1/...` URLs the Axios client builds resolve to the Vite proxy and
 * reach the live API — same-origin, exactly as the browser does it, with no
 * CORS and no request mocking.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(rootDir, 'src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    environmentOptions: {
      jsdom: {
        // The document's origin, so the pages' relative `/api` calls reach the
        // live backend through the dev server's proxy. Defaults to the port
        // vite.config.js asks for; override it when Vite had to move.
        url: process.env.SMOKE_ORIGIN || 'http://localhost:5173',
      },
    },
    include: ['src/**/*.test.{js,jsx}'],
    testTimeout: 30000,
    hookTimeout: 30000,
    // One file at a time: the suite shares a signed-in session and real
    // server state, so parallel runs would interfere.
    fileParallelism: false,
  },
})
