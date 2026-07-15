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
          path: 'clusters',
          name: 'clusters',
          component: () => import('@/views/AllClustersView.vue'),
        },
        {
          path: 'views',
          name: 'views',
          component: () => import('@/views/PlaceholderView.vue'),
          props: { title: 'Saved views', bolt: 'M9f' },
        },
        {
          path: 'scanner-status',
          name: 'scanner-status',
          component: () => import('@/views/ScannerStatusView.vue'),
          meta: { wide: true },
        },
        {
          path: 'approvals',
          name: 'approvals',
          component: () => import('@/views/ApprovalsView.vue'),
          meta: { capability: 'can_accept_audit_final', wide: true },
        },
        {
          path: 'contributors',
          name: 'contributors',
          component: () => import('@/views/ContributorsView.vue'),
          meta: { wide: true },
        },
        {
          path: 'overview',
          name: 'overview',
          component: () => import('@/views/OverviewView.vue'),
        },
        {
          path: 'findings',
          name: 'findings',
          component: () => import('@/views/FindingsView.vue'),
          meta: { wide: true },
        },
        {
          // identity = (cve_id, image_digest); scanner query = the clicked row, for header continuity
          path: 'findings/:cveId',
          name: 'finding',
          component: () => import('@/views/FindingDetailView.vue'),
        },
        {
          path: 'images',
          name: 'images',
          component: () => import('@/views/ImagesView.vue'),
          meta: { wide: true },
        },
        {
          path: 'images/:digest',
          name: 'image-detail',
          component: () => import('@/views/ImageDetailView.vue'),
          meta: { wide: true },
        },
        {
          path: 'audit',
          name: 'audit',
          component: () => import('@/views/AuditTrailView.vue'),
          meta: { wide: true },
        },
        {
          // the §13 settings shell — each child carries ITS OWN capability (the merged child
          // meta overrides the parent's, so e.g. tokens gates on can_manage_tokens alone)
          path: 'settings',
          component: () => import('@/views/settings/SettingsLayout.vue'),
          meta: { capability: 'can_manage_settings' },
          children: [
            // §13 opens on scan-scope; until slice 3 builds it, land on the first real panel
            { path: '', redirect: '/settings/sla' },
            {
              path: 'scan-scope',
              name: 'settings-scan-scope',
              component: () => import('@/views/settings/SettingsPlaceholder.vue'),
              props: {
                title: 'Scan scope',
                subtitle: 'what the scanner module discovers and scans (D43/FR-24)',
                slice: 'M9e slice 3',
              },
            },
            {
              path: 'scanning',
              name: 'settings-scanning',
              component: () => import('@/views/settings/SettingsPlaceholder.vue'),
              props: {
                title: 'Scanning',
                subtitle: 'staleness timers + read-only per-scanner provenance (C-4/D41)',
                slice: 'M9e slice 3',
              },
            },
            {
              path: 'sla',
              name: 'settings-sla',
              component: () => import('@/views/settings/SlaPolicyView.vue'),
            },
            {
              path: 'ignore-rules',
              name: 'settings-ignore-rules',
              component: () => import('@/views/settings/IgnoreRulesStub.vue'),
            },
            {
              path: 'tokens',
              name: 'settings-tokens',
              component: () => import('@/views/settings/SettingsPlaceholder.vue'),
              props: {
                title: 'Access & tokens',
                subtitle: 'scoped scanner push tokens — mint, rotate, revoke',
                slice: 'M9e slice 2',
              },
              meta: { capability: 'can_manage_tokens' },
            },
            {
              path: 'users',
              name: 'settings-users',
              component: () => import('@/views/settings/SettingsPlaceholder.vue'),
              props: {
                title: 'Users & roles',
                subtitle: 'local accounts + the four capability bundles (A-4)',
                slice: 'M9e slice 2',
              },
              meta: { capability: 'can_manage_users' },
            },
            {
              path: 'data-opensearch',
              name: 'settings-data-opensearch',
              component: () => import('@/views/settings/SettingsPlaceholder.vue'),
              props: {
                title: 'Data & OpenSearch',
                subtitle: 'retention, rollover, snapshots — drop whole indices, never delete_by_query',
                slice: 'M9e slice 4',
              },
              meta: { capability: 'can_manage_retention' },
            },
            {
              path: 'cluster',
              name: 'settings-cluster',
              component: () => import('@/views/settings/SettingsPlaceholder.vue'),
              props: {
                title: 'Cluster',
                subtitle: 'identity & ingest contract — cluster_id immutable, name relabelable',
                slice: 'M9e slice 2',
              },
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

  if (to.name === 'login') {
    return auth.isAuthed && !auth.mustChange ? { name: 'overview' } : true
  }
  if (!auth.isAuthed || auth.mustChange) return { name: 'login' }

  const cap = to.meta.capability as string | undefined
  if (cap && !auth.hasCapability(cap)) return { name: 'overview' }
  return true
})

export default router
