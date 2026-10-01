<script setup lang="ts">
import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'

import GuideProse from './GuideProse.vue'
</script>

<template>
  <GuideProse>
    <p>
      JAVV runs two scanners, <ScannerTag name="trivy" /> and <ScannerTag name="grype" />, and keeps
      their results apart. Every finding belongs to one scanner, and counts are shown per scanner, side
      by side. They're never added together, averaged or merged.
    </p>
    <p>
      The two often differ, because each uses its own vulnerability data. One may report a CVE the other
      doesn't, or rate it differently. When both report the same CVE in the same package of an image with
      different severities, the finding is marked <DisagreementBadge />. JAVV shows the disagreement; it
      doesn't decide who is right.
    </p>
    <p>Some details come from one scanner only: KEV and EPSS are reported by Grype.</p>
  </GuideProse>
</template>
