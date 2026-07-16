<script setup lang="ts">
/**
 * The Overview "Per namespace" card (issue 384 split — extracted from OverviewView): top-10
 * namespaces by findings under the scanner lens, each row a click-through to the
 * namespace-filtered grid. Per-namespace counts overlap by design (D30 — the all-namespaces
 * total is the only deduped number). Skinned by the shared base.css table (no scoped re-own).
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useOverviewStore } from '@/stores/overview'
import { countOf, fmt, type ScannerLens } from '@/lib/scannerLens'

const props = defineProps<{ scanner: ScannerLens }>()

const router = useRouter()
const overview = useOverviewStore()

const namespaces = computed(() =>
  (overview.facets.namespaces ?? [])
    .map((b) => ({ key: b.key, count: countOf(b, props.scanner) }))
    .filter((b) => b.count > 0)
    .slice(0, 10),
)

function goFindings(query: Record<string, string>) {
  void router.push({ path: '/findings', query })
}
</script>

<template>
  <section class="tbl-card">
    <div class="card-head">
      <div>
        <h3>Per namespace</h3>
        <p class="card-sub">top 10 by findings</p>
      </div>
      <UiButton variant="mini" @click="router.push('/images')">View inventory</UiButton>
    </div>
    <p v-if="namespaces.length === 0" class="empty-row">No namespace data in range.</p>
    <div v-else class="tbl-wrap">
      <table class="tbl tbl-dense tbl-hover">
        <thead>
          <tr>
            <th>Namespace</th>
            <th class="r fit">Findings</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="n in namespaces"
            :key="n.key"
            :title="`Open findings in ${n.key}`"
            @click="goFindings({ namespace: n.key })"
          >
            <td class="mono-cell ns-link">{{ n.key }}<AppIcon class="cell-go" name="chevron" :size="11" /></td>
            <td class="r fit mono-cell sm strong">{{ fmt(n.count) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 10px;
}
.card-head h3 {
  margin: 0;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.strong {
  font-weight: 700;
  color: var(--ink);
}
/* the affordance carrier — same convention as the grid's cve-link */
.ns-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .ns-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .ns-link {
    transition: none;
  }
}
</style>
