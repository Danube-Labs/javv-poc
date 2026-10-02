<script setup lang="ts">
/**
 * The identifier cell of a row that opens something, as a real link (issue 674, ruled on built
 * specimens 2026-10-02): rows answered a mouse click only, so nothing in a table could be
 * opened from the keyboard, and a screen reader found no link to follow.
 *
 * A plain click or Enter hands off to `open`, so the row keeps its ONE way of opening (some
 * rows do more than navigate: a fleet row selects its cluster first). A modified or middle
 * click is left to the browser, which opens `to` in a new tab. The click never reaches the
 * row, so a row with its own click handler does not open twice.
 */
import { computed } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'

const props = defineProps<{ to: RouteLocationRaw }>()
const emit = defineEmits<{ open: [] }>()

const router = useRouter()
const href = computed(() => router.resolve(props.to).href)

function onClick(e: MouseEvent) {
  e.stopPropagation()
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  e.preventDefault()
  emit('open')
}
</script>

<template>
  <a class="row-link" :href="href" @click="onClick"><slot /></a>
</template>

<style scoped>
/* at rest it reads exactly as the cell did; the row's own hover rules still dress the text */
.row-link {
  color: inherit;
  text-decoration: none;
  border-radius: 3px;
}
.row-link:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 2px;
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
