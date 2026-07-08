/**
 * The one place the generated client is configured. Same-origin (Vite dev proxy / the deployed
 * ingress route both put the API on our origin); the session cookie is httpOnly and rides
 * automatically. A 503 anywhere flips the global degraded flag (observability.md §3 — the app
 * degrades loudly, not blindly); the health store's /readyz poll clears it.
 */
import { client } from './generated/client.gen'
import { useHealthStore } from '@/stores/health'

client.setConfig({ baseUrl: '', credentials: 'same-origin', throwOnError: false })

client.interceptors.response.use((response) => {
  if (response.status === 503) useHealthStore().markDegraded()
  return response
})

export { client }
