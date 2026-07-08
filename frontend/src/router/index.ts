/**
 * Route table + the auth/must_change guard. All app routes live under the AppShell layout and
 * lazy-load. Guard order (SEC-6/A-4): unauthenticated → /login; must_change → locked to /login
 * (which renders the change-password form); capability-gated routes 'hide' via nav AND reroute
 * here (client convenience — the server is the authority).
 */
import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    {
      path: '/',
      component: () => import('@/layouts/AppShell.vue'),
      children: [
        { path: '', redirect: '/overview' },
        {
          path: 'overview',
          name: 'overview',
          component: () => import('@/views/PlaceholderView.vue'),
          props: { title: 'Overview', bolt: 'M9c' },
        },
        {
          path: 'findings',
          name: 'findings',
          component: () => import('@/views/PlaceholderView.vue'),
          props: { title: 'Findings', bolt: 'M9b' },
        },
        {
          path: 'images',
          name: 'images',
          component: () => import('@/views/PlaceholderView.vue'),
          props: { title: 'Images', bolt: 'M9c' },
        },
        {
          path: 'audit',
          name: 'audit',
          component: () => import('@/views/PlaceholderView.vue'),
          props: { title: 'Audit', bolt: 'M9d' },
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/PlaceholderView.vue'),
          props: { title: 'Settings', bolt: 'M9e' },
          meta: { capability: 'can_manage_settings' },
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) await auth.fetchMe()

  if (to.name === 'login') {
    return auth.isAuthed && !auth.mustChange ? { name: 'overview' } : true
  }
  if (!auth.isAuthed || auth.mustChange) return { name: 'login' }

  const cap = to.meta.capability as string | undefined
  if (cap && !auth.hasCapability(cap)) return { name: 'overview' }
  return true
})

export default router
