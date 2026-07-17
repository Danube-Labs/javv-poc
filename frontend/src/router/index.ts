/**
 * Route table + the auth/must_change guard. All app routes live under the AppShell layout and
 * lazy-load. Guard order (SEC-6/A-4): unauthenticated → /login; must_change → locked to /login
 * (which renders the change-password form); capability-gated routes 'hide' via nav AND reroute
 * here (client convenience — the server is the authority).
 */
import { createRouter, createWebHistory } from 'vue-router'

import { resolveGate } from '@/router/guards'
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
          path: 'clusters',
          name: 'clusters',
          component: () => import('@/views/AllClustersView.vue'),
          meta: { section: 'monitor' },
        },
        {
          path: 'views',
          name: 'views',
          component: () => import('@/views/PlaceholderView.vue'),
          meta: { section: 'monitor' },
          props: { title: 'Saved views', bolt: 'M9f' },
        },
        {
          path: 'scanner-status',
          name: 'scanner-status',
          component: () => import('@/views/ScannerStatusView.vue'),
          meta: { section: 'monitor', wide: true },
        },
        {
          path: 'approvals',
          name: 'approvals',
          component: () => import('@/views/ApprovalsView.vue'),
          meta: { section: 'audit', capability: 'can_accept_audit_final', wide: true },
        },
        {
          path: 'contributors',
          name: 'contributors',
          component: () => import('@/views/ContributorsView.vue'),
          meta: { section: 'insights', wide: true },
        },
        {
          path: 'overview',
          name: 'overview',
          component: () => import('@/views/OverviewView.vue'),
          meta: { wide: true, section: 'monitor' },
        },
        {
          path: 'findings',
          name: 'findings',
          component: () => import('@/views/FindingsView.vue'),
          meta: { section: 'monitor', wide: true },
        },
        {
          // identity = (cve_id, image_digest); scanner query = the clicked row, for header continuity
          path: 'findings/:cveId',
          name: 'finding',
          component: () => import('@/views/FindingDetailView.vue'),
          meta: { section: 'monitor', wide: true },
        },
        {
          path: 'images',
          name: 'images',
          component: () => import('@/views/ImagesView.vue'),
          meta: { section: 'inventory', wide: true },
        },
        {
          path: 'images/:digest',
          name: 'image-detail',
          component: () => import('@/views/ImageDetailView.vue'),
          meta: { section: 'inventory', wide: true },
        },
        {
          path: 'audit',
          name: 'audit',
          component: () => import('@/views/AuditTrailView.vue'),
          meta: { section: 'audit', wide: true },
        },
        {
          // the §13 settings shell — each child carries ITS OWN capability (the merged child
          // meta overrides the parent's, so e.g. tokens gates on can_manage_tokens alone)
          path: 'settings',
          component: () => import('@/views/settings/SettingsLayout.vue'),
          meta: { section: 'configure', capability: 'can_manage_settings' },
          children: [
            // §13 order: settings opens on scan-scope
            { path: '', redirect: '/settings/scan-scope' },
            {
              path: 'scan-scope',
              name: 'settings-scan-scope',
              component: () => import('@/views/settings/ScanScopeView.vue'),
            },
            {
              path: 'scanning',
              name: 'settings-scanning',
              component: () => import('@/views/settings/ScanningView.vue'),
            },
            {
              path: 'sla',
              name: 'settings-sla',
              component: () => import('@/views/settings/SlaPolicyView.vue'),
            },
            // 13.4 by ruling: NO nav entry — ignore rules ARE decisions; the old URL just lands there
            { path: 'ignore-rules', redirect: '/approvals' },
            {
              path: 'tokens',
              name: 'settings-tokens',
              component: () => import('@/views/settings/TokensView.vue'),
              meta: { capability: 'can_manage_tokens' },
            },
            {
              path: 'users',
              name: 'settings-users',
              component: () => import('@/views/settings/UsersRolesView.vue'),
              meta: { capability: 'can_manage_users' },
            },
            {
              path: 'data-opensearch',
              name: 'settings-data-opensearch',
              component: () => import('@/views/settings/DataOpenSearchView.vue'),
              meta: { capability: 'can_manage_retention' },
            },
            {
              path: 'cluster',
              name: 'settings-cluster',
              component: () => import('@/views/settings/ClusterView.vue'),
            },
          ],
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) await auth.fetchMe()
  return resolveGate(auth, to)
})

export default router
