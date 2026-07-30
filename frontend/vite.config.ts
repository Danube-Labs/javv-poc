import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // `coverage/` is vitest output, gitignored and never imported. Watched, it cost a full page
    // reload PER FILE written — 80 of them on one `npm run test:ci` — so running the suite while
    // the dev server was up wiped whatever the operator had on screen mid-session.
    watch: { ignored: ['**/coverage/**'] },
    proxy: {
      // the live dev backend (uvicorn :8000) — same paths the k8s ingress will route
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/readyz': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
    },
  },
  preview: {
    // the CI route smoke (scripts/ci-smoke.mjs) serves the BUILT app via `vite preview`,
    // which does not inherit server.proxy — same backend, same ingress-shaped paths
    proxy: {
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/readyz': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
    },
  },
})
