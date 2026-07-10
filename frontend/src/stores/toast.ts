/**
 * THE app-wide confirmation channel: any component/store calls `success/error/info` and the
 * single ToastStack in AppShell renders it. Auto-dismisses (errors linger longer), stack is
 * capped (oldest drops first). Errors that already have an inline, contextual home (form
 * validation, save errors next to the button) stay inline — toasts are for outcomes the user
 * would otherwise have to hunt for.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastKind = 'success' | 'error' | 'info'
export interface Toast {
  id: number
  kind: ToastKind
  message: string
}

const AUTO_DISMISS_MS: Record<ToastKind, number> = { success: 4000, info: 5000, error: 8000 }
const MAX_STACK = 4

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])
  let seq = 0
  const timers = new Map<number, ReturnType<typeof setTimeout>>()

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
    const timer = timers.get(id)
    if (timer !== undefined) {
      clearTimeout(timer)
      timers.delete(id)
    }
  }

  function push(kind: ToastKind, message: string): number {
    const id = ++seq
    toasts.value = [...toasts.value, { id, kind, message }]
    while (toasts.value.length > MAX_STACK) dismiss(toasts.value[0]!.id)
    timers.set(
      id,
      setTimeout(() => dismiss(id), AUTO_DISMISS_MS[kind]),
    )
    return id
  }

  const success = (message: string) => push('success', message)
  const error = (message: string) => push('error', message)
  const info = (message: string) => push('info', message)

  return { toasts, push, dismiss, success, error, info }
})
