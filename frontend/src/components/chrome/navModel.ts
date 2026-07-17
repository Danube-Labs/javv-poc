/**
 * The one nav model (M9f): SideNav renders it, the command palette jumps through it —
 * one source so a screen can never be reachable in one and missing in the other.
 * Structure mirrors the prototype Sidebar (main.jsx); capability-gated items hide via
 * `visibleNav` (A-4 — client convenience, the route guard + server stay the authority).
 */
import type { IconName } from '@/components/ui/AppIcon.vue'

export interface NavItem {
  label: string
  to: string
  icon: IconName
  capability?: string
}

export interface NavGroup {
  group: string
  accent: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    group: 'Monitor',
    accent: 'var(--sect-monitor)',
    items: [
      { label: 'All clusters', to: '/clusters', icon: 'layers' },
      { label: 'Overview', to: '/overview', icon: 'grid' },
      { label: 'Findings', to: '/findings', icon: 'list' },
      { label: 'Saved views', to: '/views', icon: 'bookmark' },
      { label: 'Scanner status', to: '/scanner-status', icon: 'pulse' },
    ],
  },
  { group: 'Inventory', accent: 'var(--sect-inventory)', items: [{ label: 'Running images', to: '/images', icon: 'cube' }] },
  {
    group: 'Audit',
    accent: 'var(--sect-audit)',
    items: [
      {
        label: 'Approval list',
        to: '/approvals',
        icon: 'shield',
        capability: 'can_accept_audit_final',
      },
      { label: 'Audit log', to: '/audit', icon: 'clock' },
    ],
  },
  { group: 'Insights', accent: 'var(--sect-insights)', items: [{ label: 'Contributors', to: '/contributors', icon: 'award' }] },
  {
    group: 'Configure',
    accent: 'var(--sect-configure)',
    items: [{ label: 'Settings', to: '/settings', icon: 'gear', capability: 'can_manage_settings' }],
  },
]

export function visibleNav(hasCapability: (cap: string) => boolean): NavGroup[] {
  return NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.capability || hasCapability(i.capability)),
  })).filter((g) => g.items.length > 0)
}
