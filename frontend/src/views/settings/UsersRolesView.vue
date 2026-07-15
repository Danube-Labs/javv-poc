<script setup lang="ts">
/**
 * Users & roles panel (§13.6; prototype screens-config.jsx `users` section). Ruled prototype
 * deltas (row 8/A-4): DISABLE, never delete (no delete API — the trash icon is gone); "Invite"
 * = create-with-temp-password (the user must change it at first login, SEC-6); the roles card
 * renders the capability BUNDLES from `system-roles` content (not the v4 5-role matrix) so a
 * seeded 5th role appears without a client change. A role change REVOKES the user's sessions
 * (D33) — the confirm dialog says so. 409 on the last enabled admin renders inline.
 */
import { ref } from 'vue'

import {
  createUserApiV1AdminUsersPost,
  listRolesApiV1AdminRolesGet,
  listUsersApiV1AdminUsersGet,
  passwordResetApiV1AdminUsersUsernamePasswordResetPost,
  setDisabledApiV1AdminUsersUsernameDisabledPatch,
  setRoleApiV1AdminUsersUsernameRolePatch,
} from '@/api/generated'
import { client } from '@/api/client'
import DotWord from '@/components/chips/DotWord.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

interface UserRow {
  username: string
  role: string
  capabilities: string[]
  must_change: boolean
  disabled: boolean
  auth_source: string
  created_at: string | null
}
interface RoleRow {
  role: string
  capabilities: string[]
}

const auth = useAuthStore()
const toast = useToastStore()

const users = ref<UserRow[]>([])
const roles = ref<RoleRow[]>([])
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

async function load() {
  loading.value = true
  const [u, r] = await Promise.all([
    listUsersApiV1AdminUsersGet({ client, query: { size: 1000 } }),
    listRolesApiV1AdminRolesGet({ client }),
  ])
  loading.value = false
  failed.value = !u.response?.ok || !r.response?.ok
  if (failed.value) {
    logger.warn('users_load_failed', { users: u.response?.status, roles: r.response?.status })
    return
  }
  users.value = (u.data as { users: UserRow[] }).users
  roles.value = (r.data as { roles: RoleRow[] }).roles
}
void load()

/** Server messages (409 last-admin, 422 policy) surface VERBATIM — the backend speaks RFC-7807
 * and an HTTPException's text lands in the problem's `title`. Pydantic validation 422s only say
 * "Validation error" (their detail is a repr, not user copy) — those get the caller's fallback.
 * The hey-api client already consumed the body: read the parsed `error`, never `response`. */
function detailOr(error: unknown, fallback: string): string {
  const title = (error as { title?: unknown } | undefined)?.title
  return typeof title === 'string' && title !== 'Validation error' ? title : fallback
}

// ── invite (create-with-temp-password) ─────────────────────────────────────────────────
const inviteOpen = ref(false)
const inviteName = ref('')
const invitePassword = ref('')
const inviteRole = ref('viewer')
const inviteError = ref('')

function openInvite() {
  inviteName.value = ''
  invitePassword.value = ''
  inviteRole.value = 'viewer'
  inviteError.value = ''
  inviteOpen.value = true
}

async function submitInvite() {
  busy.value = true
  const { error, response } = await createUserApiV1AdminUsersPost({
    client,
    body: { username: inviteName.value.trim(), temp_password: invitePassword.value, role: inviteRole.value },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('user_create_failed', { status: response?.status })
    inviteError.value = detailOr(
      error,
      'Rejected — usernames are 3–64 chars (letters, digits, . _ -); system and fleet are reserved.',
    )
    return
  }
  inviteOpen.value = false
  toast.success(`${inviteName.value.trim()} created — they must change the temp password at first login`)
  await load()
}

// ── role change (confirm: revokes sessions) ─────────────────────────────────────────────
const roleChange = ref<{ user: UserRow; to: string } | null>(null)
const rowError = ref<{ username: string; message: string } | null>(null)

function onRolePick(user: UserRow, event: Event) {
  const to = (event.target as HTMLSelectElement).value
  if (to !== user.role) roleChange.value = { user, to }
}

async function submitRoleChange() {
  const change = roleChange.value
  if (change === null) return
  busy.value = true
  const { error, response } = await setRoleApiV1AdminUsersUsernameRolePatch({
    client,
    path: { username: change.user.username },
    body: { role: change.to },
  })
  busy.value = false
  roleChange.value = null
  if (!response?.ok) {
    logger.warn('role_change_failed', { status: response?.status })
    rowError.value = {
      username: change.user.username,
      message: detailOr(error, 'Role change failed — nothing was changed.'),
    }
    await load() // resets the select to the server truth
    return
  }
  rowError.value = null
  toast.success(`${change.user.username} is now ${change.to} — their sessions were revoked`)
  await load()
}

// ── disable / enable ────────────────────────────────────────────────────────────────────
const disableTarget = ref<UserRow | null>(null)

async function setDisabled(user: UserRow, disabled: boolean) {
  busy.value = true
  const { error, response } = await setDisabledApiV1AdminUsersUsernameDisabledPatch({
    client,
    path: { username: user.username },
    body: { disabled },
  })
  busy.value = false
  disableTarget.value = null
  if (!response?.ok) {
    logger.warn('user_disable_failed', { status: response?.status })
    rowError.value = {
      username: user.username,
      message: detailOr(error, 'The change failed — nothing was changed.'),
    }
    return
  }
  rowError.value = null
  toast.success(disabled ? `${user.username} disabled — their sessions were revoked` : `${user.username} re-enabled`)
  await load()
}

// ── password reset ──────────────────────────────────────────────────────────────────────
const resetTarget = ref<UserRow | null>(null)
const resetPassword = ref('')
const resetError = ref('')

function openReset(user: UserRow) {
  resetPassword.value = ''
  resetError.value = ''
  resetTarget.value = user
}

async function submitReset() {
  if (resetTarget.value === null) return
  busy.value = true
  const { error, response } = await passwordResetApiV1AdminUsersUsernamePasswordResetPost({
    client,
    path: { username: resetTarget.value.username },
    body: { temp_password: resetPassword.value },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('pwd_reset_failed', { status: response?.status })
    resetError.value = detailOr(error, 'The reset failed — the old password still works.')
    return
  }
  toast.success(`${resetTarget.value.username} must change the new temp password at next login`)
  resetTarget.value = null
}

const isSelf = (user: UserRow) => user.username === auth.user?.username
</script>

<template>
  <div class="stack">
    <SettingsCard
      title="Users"
      subtitle="role is granted per user — enforced on every API call, not just hidden in the UI"
    >
      <template #action>
        <UiButton :disabled="busy" @click="openInvite"><AppIcon name="plus" :size="13" />Invite user</UiButton>
      </template>

      <div v-if="loading" class="skel-block" aria-busy="true" aria-label="Loading users" />
      <p v-else-if="failed" class="load-error" role="alert">
        User list unavailable. Check the backend connection.
      </p>

      <div v-else class="usr-scroll">
        <table class="tbl">
          <thead>
            <tr><th>User</th><th>Role</th><th>Source</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            <template v-for="user in users" :key="user.username">
              <tr :class="{ 'row-off': user.disabled }">
                <td class="mono-sm">{{ user.username }}<span v-if="isSelf(user)" class="self-tag">you</span></td>
                <td>
                  <select
                    class="set-select"
                    :value="user.role"
                    :disabled="busy || user.disabled"
                    :aria-label="`Role for ${user.username}`"
                    @change="onRolePick(user, $event)"
                  >
                    <option v-for="r in roles" :key="r.role" :value="r.role">{{ r.role }}</option>
                  </select>
                </td>
                <td class="mono-sm">{{ user.auth_source }}</td>
                <td>
                  <DotWord v-if="user.disabled" tone="muted" label="disabled" />
                  <DotWord v-else-if="user.must_change" tone="warn" label="must change password" />
                  <DotWord v-else tone="ok" label="active" />
                </td>
                <td class="row-actions">
                  <UiButton
                    :disabled="busy || user.auth_source !== 'local' || user.disabled"
                    :title="user.auth_source !== 'local' ? 'Password is managed by the identity provider' : undefined"
                    @click="openReset(user)"
                  >Reset password</UiButton>
                  <UiButton v-if="user.disabled" :disabled="busy" @click="setDisabled(user, false)">Enable</UiButton>
                  <UiButton v-else :disabled="busy" @click="disableTarget = user">Disable</UiButton>
                </td>
              </tr>
              <tr v-if="rowError?.username === user.username">
                <td colspan="5" class="row-error" role="alert">{{ rowError.message }}</td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </SettingsCard>

    <SettingsCard title="Roles" subtitle="a role is a bundle of capabilities — endpoints check the capability, never the role name">
      <div v-if="!loading && !failed" class="roles-list">
        <div v-for="r in roles" :key="r.role" class="role-row">
          <span class="role-name mono-sm">{{ r.role }}</span>
          <span v-if="r.capabilities.length === 0" class="role-caps-none">read-only dashboards</span>
          <span v-else-if="r.capabilities.includes('*')" class="role-caps-all">every capability, present and future</span>
          <span v-else class="role-caps">
            <code v-for="cap in r.capabilities" :key="cap" class="cap-chip mono-sm">{{ cap }}</code>
          </span>
        </div>
      </div>
      <p class="evidence-note">
        Disable, never delete — a departed user's rows stay attributable in the audit trail.
        New bundles are seeded as <span class="mono-sm">system-roles</span> data; they appear here without a release.
      </p>
    </SettingsCard>

    <!-- invite -->
    <ModalShell v-if="inviteOpen" title="Invite a user" subtitle="they log in with the temp password and must change it" @close="inviteOpen = false">
      <UiField label="Username" first hint="3–64 chars; letters, digits, . _ -" for="inv-name">
        <SettingsInput id="inv-name" v-model="inviteName" />
      </UiField>
      <UiField label="Temp password" hint="policy-checked server-side; forced change at first login" for="inv-pass">
        <SettingsInput id="inv-pass" v-model="invitePassword" />
      </UiField>
      <UiField label="Role" for="inv-role">
        <select id="inv-role" v-model="inviteRole" class="set-select">
          <option v-for="r in roles" :key="r.role" :value="r.role">{{ r.role }}</option>
        </select>
      </UiField>
      <p v-if="inviteError" class="modal-error" role="alert">{{ inviteError }}</p>
      <template #actions>
        <UiButton variant="ghost" @click="inviteOpen = false">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy || !inviteName.trim() || !invitePassword" @click="submitInvite">
          {{ busy ? 'Creating…' : 'Create user' }}
        </UiButton>
      </template>
    </ModalShell>

    <!-- role-change confirm -->
    <ModalShell v-if="roleChange" title="Change role?" @close="roleChange = null; void load()">
      <p class="confirm-copy">
        <span class="mono-sm">{{ roleChange.user.username }}</span> becomes
        <b>{{ roleChange.to }}</b>. Their capabilities change immediately and
        <b>every active session is signed out</b> — a new role never rides an old session.
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="roleChange = null; void load()">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy" @click="submitRoleChange">
          {{ busy ? 'Changing…' : 'Change role' }}
        </UiButton>
      </template>
    </ModalShell>

    <!-- disable confirm -->
    <ModalShell v-if="disableTarget" title="Disable this user?" @close="disableTarget = null">
      <p class="confirm-copy">
        <span class="mono-sm">{{ disableTarget.username }}</span> is signed out everywhere and can no
        longer log in. Nothing is deleted — their triage history stays attributable, and you can
        re-enable them any time.<template v-if="isSelf(disableTarget)"> <b>This is your own account.</b></template>
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="disableTarget = null">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy" @click="setDisabled(disableTarget, true)">
          {{ busy ? 'Disabling…' : 'Disable' }}
        </UiButton>
      </template>
    </ModalShell>

    <!-- password reset -->
    <ModalShell
      v-if="resetTarget"
      :title="`Reset ${resetTarget.username}'s password`"
      subtitle="their sessions are revoked; the temp password must be changed at next login"
      @close="resetTarget = null"
    >
      <UiField label="Temp password" first hint="policy-checked server-side" for="rst-pass">
        <SettingsInput id="rst-pass" v-model="resetPassword" />
      </UiField>
      <p v-if="resetError" class="modal-error" role="alert">{{ resetError }}</p>
      <template #actions>
        <UiButton variant="ghost" @click="resetTarget = null">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy || !resetPassword" @click="submitReset">
          {{ busy ? 'Resetting…' : 'Reset password' }}
        </UiButton>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.usr-scroll {
  overflow-x: auto;
  margin-top: 10px;
}
.mono-sm {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}
.self-tag {
  margin-left: 8px;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--teal-text);
  background: var(--note-info-bg);
  padding: 2px 6px;
  border-radius: 5px;
}
.row-off td {
  color: var(--soft);
}
.row-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
.row-error {
  color: var(--health-down-fg);
  font-size: var(--text-sm);
}
.set-select {
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 6px 9px;
  font-size: var(--text-body);
  font-family: var(--font-ui);
  color: var(--ink);
  background: var(--card);
  min-width: 140px;
}
.set-select:hover:not(:disabled) {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.set-select:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.set-select:disabled {
  color: var(--soft);
  background: var(--panel);
  cursor: not-allowed;
}
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
.modal-error {
  margin: 10px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
.confirm-copy {
  margin: 0;
  max-width: 440px;
  line-height: 1.5;
  color: var(--ink);
}
.load-error {
  margin: 14px 0 8px;
}
.skel-block {
  height: 160px;
  margin: 14px 0 8px;
  border-radius: var(--r-sm);
  background: linear-gradient(90deg, var(--line2) 25%, var(--panel) 50%, var(--line2) 75%);
  background-size: 200% 100%;
  animation: skel-shimmer 1.4s ease-in-out infinite;
}
@keyframes skel-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .skel-block {
    animation: none;
  }
}
</style>
