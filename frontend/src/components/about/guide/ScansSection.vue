<script setup lang="ts">
import StateTag from '@/components/chips/StateTag.vue'

import GuideProse from './GuideProse.vue'
</script>

<template>
  <GuideProse>
    <ul>
      <li>
        <strong>A scan counts once it is complete.</strong> JAVV uses a scan only after all of it has
        arrived, so a half-finished scan never changes what you see.
      </li>
      <li>
        <strong>Fixed findings leave at once.</strong> When the next complete scan of an image no longer
        reports a finding, it leaves the findings tables straight away.
      </li>
      <li>
        <strong>A quiet scanner doesn't erase anything.</strong> If a scanner stops sending, its last
        results stay. A red banner names it once it has been silent longer than the freshness window
        (3 days by default). If it stays silent past the scanner-down window (7 days by default), its
        findings are marked <StateTag state="stale" />. Admins set both windows per cluster in
        <span class="ui-name">Settings › Scanning</span>.
      </li>
    </ul>
  </GuideProse>
</template>
