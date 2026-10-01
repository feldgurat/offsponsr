import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Where `offsponsr --dev` serves the API. Mirrored in src/offsponsr/app.py (DEV_API_PORT),
// as is the dev server port below (DEV_FRONTEND_ORIGIN).
const DEV_API = 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    // The Python app serves the bundle from its package directory.
    outDir: '../src/offsponsr/web',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': DEV_API,
      '/media': DEV_API,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
  },
})
