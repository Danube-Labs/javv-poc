<script setup lang="ts">
/**
 * Per-scanner evidence table (split from FindingDetailView, audit F-15): the returned pair
 * rows ARE the evidence — one row per scanner, never reconciled (A-3); absent scanners get
 * an explicit absent-row, and verbatim severities that differ from canonical show quoted.
 */
import EpssBar from '@/components/chips/EpssBar.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import StateTag from '@/components/chips/StateTag.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { fmtAt, num } from '@/findings/format'
import type { FindingRow } from '@/stores/findings'

defineProps<{
  evidence: FindingRow[]
  missingScanners: string[]
  disagrees: boolean
  otherPackages: string[]
}>()

function verbatimDiffers(r: FindingRow): boolean {
  return r.severity.toLowerCase() !== r.severity_canonical
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>Per-scanner evidence</h3>
        <p class="card-sub">raw results, no black box</p>
      </div>
      <span class="card-tag">no cross-scanner merge</span>
    </div>
    <div class="card-body">
      <table class="dtbl dtbl-bordered">
        <thead>
          <tr>
            <th>Scanner</th><th>Severity</th><th>CVSS</th><th>Package</th><th>Fixed in</th>
            <th>EPSS</th><th>State</th><th>Last seen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in evidence" :key="r.finding_key">
            <td><ScannerTag :name="r.scanner" /></td>
            <td>
              <SevChip :level="r.severity_canonical" />
              <span v-if="verbatimDiffers(r)" class="mono-cell sm verbatim" :title="'verbatim from ' + r.scanner">“{{ r.severity }}”</span>
            </td>
            <td class="mono-cell sm">{{ num(r.cvss) }}</td>
            <td class="mono-cell sm">{{ r.package_name }}</td>
            <td>
              <span v-if="r.fixed_version" class="mono-cell sm ver-fix">{{ r.fixed_version }}</span>
              <span v-else class="ver-none">no fix</span>
            </td>
            <td><EpssBar :v="r.epss" /></td>
            <td><StateTag :state="r.state" /></td>
            <td class="mono-cell sm">{{ fmtAt(r.last_seen_at) }}</td>
          </tr>
          <tr v-for="s in missingScanners" :key="s" class="absent-row">
            <td><ScannerTag :name="s" /></td>
            <td colspan="7" class="absent-note">
              no current finding from this scanner for this CVE on this image
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="disagrees" class="evidence-note evidence-warn">
        <AppIcon name="alert" :size="12" /> The scanners disagree. Both verdicts shown
        verbatim; JAVV never picks a winner.
      </p>
      <p v-else class="evidence-note">
        Scanners agree on severity. Dashboards facet by scanner so this finding is never
        double-counted.
      </p>
      <p v-if="otherPackages.length" class="evidence-note">
        This CVE also affects
        <span class="mono-cell sm">{{ otherPackages.slice(0, 5).join(', ') }}</span><template v-if="otherPackages.length > 5"> +{{ otherPackages.length - 5 }} more</template> on this image;
        open those rows from the grid.
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
.card-tag {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.04em;
  color: var(--teal-text);
  background: var(--note-info-bg);
  padding: 4px 8px;
  border-radius: 6px;
  text-transform: uppercase;
  flex: none;
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
.evidence-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}

.verbatim {
  margin-left: 8px;
  color: var(--soft);
}
.ver-fix {
  color: var(--teal-text);
}
.ver-none {
  color: var(--ver-none-fg);
  font-style: italic;
  font-size: var(--text-sm);
}
.absent-row td {
  background: var(--panel);
}
.absent-note {
  color: var(--soft);
  font-size: var(--text-sm);
}
.evidence-warn {
  color: var(--ink);
}
.evidence-warn svg {
  color: var(--sev-high-fg);
  flex: none;
}
</style>
