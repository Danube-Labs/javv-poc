<script setup lang="ts">
/**
 * The person atom (M9d slice 3; Nuxt UUser composition on our tokens): initials avatar +
 * stacked name / quiet secondary — ONE atom for the podium, the leaderboard person column,
 * and the activity feed, so a contributor reads identically everywhere. The wire carries only
 * a username: initials + the deterministic categorical tone are presentation (viewModel.ts),
 * never invented data — no roles, no photos.
 */
import { computed } from 'vue'

import { actorTone, initials } from '@/contributors/viewModel'

const props = withDefaults(
  defineProps<{
    actor: string
    /** quiet secondary line under the name (honest wire facts only, e.g. "12 actions") */
    sub?: string
    size?: number
    /** avatar above the name (podium) instead of beside it */
    vertical?: boolean
  }>(),
  { sub: '', size: 30, vertical: false },
)

const tone = computed(() => actorTone(props.actor))
const label = computed(() => initials(props.actor))
</script>

<template>
  <div class="cid" :class="{ 'cid-vertical': vertical }">
    <span
      class="cid-av"
      :style="{ background: tone, width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.36)}px` }"
      aria-hidden="true"
      >{{ label }}</span
    >
    <div class="cid-id">
      <span class="cid-name">{{ actor }}</span>
      <span v-if="sub" class="cid-sub">{{ sub }}</span>
    </div>
  </div>
</template>

<style scoped>
/* prototype .lb-person / .hero-av structure on tokens */
.cid {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.cid-vertical {
  flex-direction: column;
  gap: 0;
  text-align: center;
}
.cid-av {
  border-radius: 50%;
  color: var(--card);
  display: inline-grid;
  place-items: center;
  font-weight: 600;
  letter-spacing: 0.02em;
  flex: none;
  user-select: none;
}
.cid-id {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  min-width: 0;
}
.cid-vertical .cid-id {
  align-items: center;
  margin-top: 9px;
}
.cid-name {
  font-weight: 600;
  font-size: var(--text-body);
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cid-sub {
  font-size: var(--text-control);
  color: var(--soft);
}
</style>
