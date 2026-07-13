<script setup lang="ts">
/**
 * Affected components table (split from FindingDetailView, audit F-15): every occurrence of
 * the CVE across the last committed inventory — one row per image + package, scanners listed,
 * never merged. Truncation is said out loud (honest data), never silently.
 */
import ScannerTag from '@/components/chips/ScannerTag.vue'
import type { AffectedComponentRow } from '@/findings/detailViewModel'

defineProps<{
  affected: AffectedComponentRow[]
  truncated: boolean
}>()
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>Affected components <span class="count-badge">{{ affected.length }}{{ truncated ? '+' : '' }}</span></h3>
        <p class="card-sub">across the last committed inventory · one row per image + package, scanners listed, never merged</p>
      </div>
    </div>
    <div class="card-body">
      <div class="img-scroll">
      <table class="dtbl dtbl-bordered">
        <thead>
          <tr><th>Image</th><th>Namespace</th><th>Package</th><th>Current</th><th>Fixed</th><th>Scanners</th></tr>
        </thead>
        <tbody>
          <tr v-if="affected.length === 0"><td colspan="6" class="empty-row">No occurrences returned.</td></tr>
          <tr v-for="a in affected" :key="`${a.image}|${a.packageName}|${a.current}|${a.fixed}`">
            <td class="mono-cell strong">{{ a.image }}</td>
            <td class="mono-cell sm">{{ a.namespaces.join(', ') || '—' }}</td>
            <td class="mono-cell sm">{{ a.packageName }}</td>
            <td class="mono-cell sm">{{ a.current ?? '—' }}</td>
            <td class="mono-cell sm" :class="{ 'no-fix': !a.fixed }">{{ a.fixed ?? 'no fix' }}</td>
            <td><ScannerTag v-for="s in a.scanners" :key="s" :name="s" class="scn-gap" /></td>
          </tr>
        </tbody>
      </table>
      </div>
      <p v-if="truncated" class="evidence-note">
        Showing the first {{ affected.length }} components — more exist. Narrow via the
        Findings grid (search the CVE id).
      </p>
      <p class="evidence-note">
        A package listed by one scanner only, or twice with different versions, is a scanner
        disagreement — not a clean bill. Workload names land with the envelope (v1.1).
      </p>
    </div>
  </section>
</template>

<style scoped>
/* the detail-card chrome + dtbl family (scoped per component — the DecisionsCard idiom) */
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line2);
}
.card-head h3 {
  margin: 0;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-body {
  padding: 14px 16px;
  overflow-x: auto;
}
.dtbl {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-mono-cell);
}
.dtbl th {
  text-align: left;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--soft);
  font-weight: 400;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
}
.dtbl td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line2);
  vertical-align: middle;
}
.dtbl tr:last-child td {
  border-bottom: 0;
}
.dtbl-bordered td,
.dtbl-bordered th {
  border-right: 1px solid var(--line2);
}
.dtbl-bordered td:last-child,
.dtbl-bordered th:last-child {
  border-right: 0;
}
.dtbl .sm {
  font-size: var(--text-sm);
}
.mono-cell {
  font-family: var(--font-mono);
}
.strong {
  font-weight: 700;
}
.evidence-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
.count-badge {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 400;
  color: var(--soft);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-chip);
  padding: 2px 7px;
  margin-left: 6px;
  vertical-align: 2px;
}
/* 100+ images must not become a wall — the table scrolls inside its viewport (≈9 rows) */
.img-scroll {
  max-height: 340px;
  overflow-y: auto;
}
.img-scroll thead th {
  position: sticky;
  top: 0;
  background: var(--card);
  z-index: 1;
}
.no-fix {
  color: var(--soft);
  font-style: italic;
}
.scn-gap {
  margin-right: 4px;
}
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 28px 12px;
}
</style>
