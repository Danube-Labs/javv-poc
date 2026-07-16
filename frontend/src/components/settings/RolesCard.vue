<script setup lang="ts">
/**
 * The Roles card (issue 384 split — extracted from UsersRolesView, no behavior change):
 * renders the capability BUNDLES from `system-roles` content (A-4 — not the v4 5-role
 * matrix), so a seeded 5th role appears without a client change. Display-only.
 */
import SettingsCard from '@/components/settings/SettingsCard.vue'

export interface RoleRow {
  role: string
  capabilities: string[]
}

defineProps<{ roles: RoleRow[]; ready: boolean }>()
</script>

<template>
  <SettingsCard title="Roles" subtitle="a role is a bundle of capabilities — endpoints check the capability, never the role name">
    <div v-if="ready" class="roles-list">
      <div v-for="r in roles" :key="r.role" class="role-row">
        <span class="role-name mono-cell sm">{{ r.role }}</span>
        <span v-if="r.capabilities.length === 0" class="role-caps-none">read-only dashboards</span>
        <span v-else-if="r.capabilities.includes('*')" class="role-caps-all">every capability, present and future</span>
        <span v-else class="role-caps">
          <code v-for="cap in r.capabilities" :key="cap" class="cap-chip mono-cell sm">{{ cap }}</code>
        </span>
      </div>
    </div>
    <p class="evidence-note">
      Disable, never delete — a departed user's rows stay attributable in the audit trail.
      New bundles are seeded as <span class="mono-cell sm">system-roles</span> data; they appear here without a release.
    </p>
  </SettingsCard>
</template>

<style scoped>
.roles-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
}
.role-row {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px solid var(--line2);
}
.role-row:last-child {
  border-bottom: 0;
}
.role-name {
  flex: none;
  width: 120px;
  font-weight: 700;
  color: var(--ink);
}
.role-caps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cap-chip {
  padding: 2px 7px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: 5px;
  color: var(--ink);
}
.role-caps-none,
.role-caps-all {
  font-size: var(--text-sm);
  color: var(--soft);
}
.evidence-note {
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
</style>
