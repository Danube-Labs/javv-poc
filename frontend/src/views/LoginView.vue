<script setup lang="ts">
/**
 * Login + forced password change (SCREENS §0). Error copy is GENERIC — never a
 * user-existence hint; 429 lockout copy gives no countdown oracle. A must_change session is
 * locked here (mode 'change') until the password is rotated (SEC-6).
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import icon from '@/assets/brand/icon.svg'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const newPassword = ref('')
const confirm = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

const mode = computed(() => (auth.mustChange ? 'change' : 'login'))

async function submitLogin() {
  busy.value = true
  error.value = await auth.login(username.value, password.value)
  busy.value = false
  if (error.value === null && !auth.mustChange) await router.push('/overview')
}

async function submitChange() {
  if (newPassword.value !== confirm.value) {
    error.value = 'New passwords do not match.'
    return
  }
  busy.value = true
  error.value = await auth.changePassword(password.value, newPassword.value)
  busy.value = false
  if (error.value === null) await router.push('/overview')
}
</script>

<template>
  <main class="login-page">
    <form class="card" @submit.prevent="mode === 'login' ? submitLogin() : submitChange()">
      <div class="login-brand">
        <img :src="icon" alt="" width="44" height="44" />
        <span class="brand-word"><b>javv</b><span>by Danube Labs</span></span>
      </div>
      <p class="tagline">just another vulnerability viewer</p>

      <template v-if="mode === 'login'">
        <label for="username">Username</label>
        <input id="username" v-model="username" autocomplete="username" required />
        <label for="password">Password</label>
        <input id="password" v-model="password" type="password" autocomplete="current-password" required />
      </template>

      <template v-else>
        <p class="notice">Your password must be changed before continuing.</p>
        <label for="current">Current password</label>
        <input id="current" v-model="password" type="password" autocomplete="current-password" required />
        <label for="new">New password</label>
        <input id="new" v-model="newPassword" type="password" autocomplete="new-password" required />
        <label for="confirm">Confirm new password</label>
        <input id="confirm" v-model="confirm" type="password" autocomplete="new-password" required />
      </template>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="busy">
        {{ mode === 'login' ? 'Sign in' : 'Change password' }}
      </button>
    </form>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.card {
  display: flex;
  flex-direction: column;
  width: 340px;
  padding: 28px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 11px;
}
.brand-word {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}
.brand-word b {
  font-size: var(--text-brand-word);
  letter-spacing: -0.03em;
}
.brand-word span {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--soft);
  letter-spacing: 0.04em;
  margin-top: 2px;
}
.tagline {
  margin: 2px 0 18px;
  color: var(--soft);
  font-size: var(--text-body);
}
.notice {
  padding: 8px 10px;
  margin: 0 0 12px;
  background: var(--state-open-bg);
  color: var(--ink);
  border: 1px solid var(--state-open-line);
  border-radius: var(--r-chip);
  font-size: var(--text-body);
}
label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--soft);
  margin: 10px 0 4px;
}
input {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: var(--text-body);
  background: var(--panel);
  color: var(--ink);
}
.error {
  margin: 12px 0 0;
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
button {
  margin-top: 18px;
  padding: 9px;
  border: none;
  border-radius: var(--r-sm);
  background: var(--coral);
  color: var(--card);
  font-family: var(--font-ui);
  font-size: var(--text-body);
  font-weight: 600;
  cursor: default;
  transition: background 0.12s;
}
button:hover:not(:disabled) {
  background: var(--coral-d);
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
