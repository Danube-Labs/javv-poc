/* JAVV - placeholder demo dataset (lorem / boilerplate, no real identifiers). window.JAVV */
(function () {
  const SEV = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];

  // ---- Top-line counts ----
  const severityTotals = { CRITICAL: 119, HIGH: 1793, MEDIUM: 4396, LOW: 467, UNKNOWN: 22 };
  const new30d = { CRITICAL: 10, HIGH: 117, MEDIUM: 554, LOW: 85 };

  // ---- Namespaces (placeholder) ----
  const namespaces = [
    { ns: "lorem-ipsum", crit: 14, high: 995, low: 196, med: 2959, images: 6 },
    { ns: "dolor-sit-amet", crit: 7, high: 372, low: 116, med: 1314, images: 4 },
    { ns: "consectetur", crit: 13, high: 283, low: 147, med: 1291, images: 5 },
    { ns: "adipiscing-elit", crit: 9, high: 216, low: 42, med: 341, images: 3 },
    { ns: "sed-eiusmod", crit: 14, high: 214, low: 94, med: 1019, images: 8 },
    { ns: "tempor-incididunt", crit: 31, high: 166, low: 39, med: 184, images: 11 },
    { ns: "labore-dolore", crit: 7, high: 155, low: 84, med: 916, images: 2 },
    { ns: "magna-aliqua", crit: 6, high: 142, low: 30, med: 410, images: 4 },
    { ns: "enim-veniam", crit: 4, high: 121, low: 51, med: 388, images: 5 },
    { ns: "quis-nostrud", crit: 2, high: 88, low: 22, med: 233, images: 7 },
  ];

  // ---- Applications ----
  const applications = [
    { app: "lorem", crit: 19, high: 180, low: 77, med: 286 },
    { app: "ipsum", crit: 31, high: 166, low: 39, med: 184 },
    { app: "dolor", crit: 18, high: 244, low: 107, med: 1038 },
    { app: "amet", crit: 2, high: 49, low: 10, med: 55 },
    { app: "elit", crit: 34, high: 275, low: 106, med: 411 },
    { app: "tempor", crit: 21, high: 387, low: 205, med: 1438 },
    { app: "magna", crit: 63, high: 1358, low: 354, med: 3840 },
    { app: "veniam", crit: 0, high: 17, low: 4, med: 28 },
  ];

  // ---- Package type breakdown ----
  const packageTypes = [
    { name: "debian", value: 73.88 },
    { name: "jar", value: 6.29 },
    { name: "gobinary", value: 4.43 },
    { name: "python", value: 4.1 },
    { name: "photon", value: 3.6 },
    { name: "node-pkg", value: 2.9 },
    { name: "alpine", value: 2.3 },
    { name: "gem", value: 1.4 },
    { name: "rust-binary", value: 1.1 },
  ];

  // ---- Language-specific binaries ----
  const languageBinaries = [
    { path: "Java", count: 452 },
    { path: "lorem/bin/ipsum", count: 204 },
    { path: "dolor-provisioner", count: 138 },
    { path: "amet-attacher", count: 133 },
    { path: "sit-registrar", count: 131 },
    { path: "elit-resizer", count: 119 },
    { path: "tempor/bin/magna", count: 102 },
    { path: "Python", count: 91 },
    { path: "aliqua-controller", count: 91 },
  ];

  // ---- Top components ----
  const topComponents = [
    { name: "lorem-api", avg: 4178, min: 4119, max: 4186, last: 4185 },
    { name: "ipsum-web", avg: 1762, min: 1703, max: 1772, last: 1770 },
    { name: "dolor-svc", avg: 1586, min: 1334, max: 1639, last: 1639 },
    { name: "sit-worker", avg: 1287, min: 1020, max: 1341, last: 1341 },
    { name: "amet-gateway", avg: 1110, min: 858, max: 1163, last: 1163 },
    { name: "elit-cache", avg: 513, min: 513, max: 513, last: 513 },
    { name: "tempor-proxy", avg: 342, min: 341, max: 346, last: 346 },
    { name: "labore-queue", avg: 307, min: 307, max: 309, last: 309 },
  ];

  // ---- Time series ----
  const days = [];
  const today = new Date("2026-06-03T00:00:00Z");
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today.getTime() - i * 86400000);
    days.push(d.toISOString().slice(5, 10));
  }
  function ramp(base, start, jitter) {
    return days.map((_, i) => {
      const t = i / (days.length - 1);
      const v = start + (base - start) * Math.min(1, t * 1.4);
      return Math.round(v + (Math.sin(i * 1.7) * jitter));
    });
  }
  const severitySeries = {
    days,
    CRITICAL: ramp(119, 110, 2),
    HIGH: ramp(1793, 1690, 14),
    MEDIUM: ramp(4396, 4180, 30),
    LOW: ramp(467, 300, 8),
  };
  const publishedSeries = days.map((d, i) => {
    const spikes = { 2: 18, 3: 158, 4: 12, 5: 126, 13: 34, 24: 188, 25: 104 };
    return spikes[i] || Math.round(Math.abs(Math.sin(i * 2.3)) * 14);
  });

  // ---- Synthesize findings ----
  const components = [
    "lorem-api", "ipsum-web", "dolor-svc", "sit-worker", "amet-gateway",
    "elit-cache", "tempor-proxy", "labore-queue", "magna-store",
    "aliqua-auth", "veniam-stream", "nostrud-db",
  ];
  const packages = [
    ["liblorem", "debian"], ["ipsum-ssl", "debian"], ["dolor-libc", "debian"], ["sit-xml", "debian"],
    ["amet-glib", "photon"], ["consectetur-archive", "photon"], ["elit-tls", "photon"], ["sed-py", "photon"],
    ["tempor-krb", "photon"], ["labore-zlib", "alpine"], ["magna-curl", "alpine"], ["aliqua-json", "jar"],
    ["veniam-log", "jar"], ["nostrud-net", "jar"], ["lorem-go", "gobinary"],
    ["ipsum-req", "python"], ["dolor-url", "python"], ["amet-dash", "node-pkg"],
  ];
  const scanners = ["Trivy", "Grype"];
  const states = ["open", "open", "open", "stale", "acknowledged", "resolved"];
  const namespacesFlat = namespaces.map((n) => n.ns);

  function ver() { return `${1 + (Math.random() * 3 | 0)}.${(Math.random() * 40 | 0)}.${(Math.random() * 20 | 0)}`; }
  function pad(n, w) { return String(n).padStart(w, "0"); }

  const sevByWeight = () => {
    const r = Math.random();
    if (r < 0.06) return "CRITICAL";
    if (r < 0.34) return "HIGH";
    if (r < 0.85) return "MEDIUM";
    if (r < 0.97) return "LOW";
    return "UNKNOWN";
  };
  const slaForSev = (s) => ({ CRITICAL: 2, HIGH: 7, MEDIUM: 30, LOW: 90, UNKNOWN: 90 }[s]);

  const findings = [];
  let seed = 42;
  function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }

  const assigneePool = [
    { name: "Lorem Ipsum", initials: "LI", tone: "#C0271D" },
    { name: "Dolor Sit", initials: "DS", tone: "#1F8E84" },
    { name: "Amet Consectetur", initials: "AC", tone: "#3D7DA6" },
    { name: "Adipiscing Elit", initials: "AE", tone: "#7A5BA8" },
    { name: "Sed Eiusmod", initials: "SE", tone: "#C2540D" },
  ];

  // placeholder advisory IDs (synthetic, not real CVEs)
  const curatedCves = [
    "CVE-2024-10011", "CVE-2024-10042", "CVE-2024-10077", "CVE-2025-20013",
    "CVE-2026-30041", "CVE-2026-30058", "CVE-2025-20119", "CVE-2025-20204",
    "CVE-2025-20217", "ADV-2026-0007", "CVE-2024-10310", "CVE-2024-10422",
    "CVE-2025-20455", "CVE-2026-30501", "CVE-2025-20533", "ADV-2025-0019",
  ];

  for (let i = 0; i < 84; i++) {
    const sev = i < 12 ? (i < 8 ? "CRITICAL" : "HIGH") : sevByWeight();
    const [pkg, ptype] = packages[(rnd() * packages.length) | 0];
    const comp = components[(rnd() * components.length) | 0];
    const scanner = scanners[(rnd() * scanners.length) | 0];
    const ns = namespacesFlat[(rnd() * namespacesFlat.length) | 0];
    const cve = i < curatedCves.length ? curatedCves[i] : `CVE-${2024 + ((rnd() * 3) | 0)}-${pad(10000 + ((rnd() * 40000) | 0), 5)}`;
    const epss = sev === "CRITICAL" ? 0.4 + rnd() * 0.59 : sev === "HIGH" ? 0.05 + rnd() * 0.6 : rnd() * 0.2;
    const kev = sev === "CRITICAL" ? rnd() > 0.55 : sev === "HIGH" ? rnd() > 0.85 : false;
    const hasFix = rnd() > 0.18;
    const cur = ver();
    const state = sev === "CRITICAL" && i < 6 ? "open" : states[(rnd() * states.length) | 0];
    const slaDays = slaForSev(sev);
    const overdue = sev === "CRITICAL" && rnd() > 0.4;
    const assignee = (state === "resolved" || state === "acknowledged" || rnd() > 0.4) ? assigneePool[(rnd() * assigneePool.length) | 0] : null;
    const disagree = rnd() > 0.86 ? ({ CRITICAL: "HIGH", HIGH: "MEDIUM", MEDIUM: "LOW" }[sev] || null) : null;
    findings.push({
      id: i, cve, severity: sev, epss: +epss.toFixed(2), kev,
      component: comp, pkg, ptype, scanner, ns, current: cur,
      fixed: hasFix ? `${cur.split(".").slice(0, 2).join(".")}.${(cur.split(".")[2] | 0) + 3}` : null,
      sla: slaDays, slaDeadline: overdue ? "overdue" : `${slaDays}d`, overdue, state,
      images: 1 + ((rnd() * 6) | 0), published: days[(rnd() * days.length) | 0], assignee, disagree,
    });
  }

  // ---- Running images ----
  const images = [
    { app: "magna", name: "lorem-api", tag: "v1.4.0", registry: "registry.example.com/group", ns: "lorem-ipsum", replicas: 4, crit: 8, high: 612, med: 2789, low: 121, total: 4187, fixable: 2596, scanners: ["Trivy", "Grype"], seenRel: "5h ago", seenAbs: "Jun 12, 07:00", running: true },
    { app: "magna", name: "ipsum-web", tag: "v4.8.1", registry: "registry.example.com/group", ns: "dolor-sit-amet", replicas: 3, crit: 5, high: 248, med: 1182, low: 88, total: 1773, fixable: 1099, scanners: ["Trivy", "Grype"], seenRel: "5h ago", seenAbs: "Jun 12, 07:00", running: true },
    { app: "magna", name: "dolor-svc", tag: "v1.0.0", registry: "registry.example.com/group", ns: "labore-dolore", replicas: 2, crit: 7, high: 155, med: 916, low: 84, total: 1163, fixable: 721, scanners: ["Trivy", "Grype"], seenRel: "9h ago", seenAbs: "Jun 12, 03:00", running: true },
    { app: "magna", name: "sit-worker", tag: "v1.1.2", registry: "registry.example.com/group", ns: "adipiscing-elit", replicas: 2, crit: 9, high: 216, med: 341, low: 42, total: 513, fixable: 318, scanners: ["Trivy", "Grype"], seenRel: "9h ago", seenAbs: "Jun 12, 03:00", running: true },
    { app: "magna", name: "amet-gateway", tag: "v8.3.0", registry: "registry.example.com/group", ns: "lorem-ipsum", replicas: 1, crit: 1, high: 38, med: 142, low: 24, total: 225, fixable: 140, scanners: ["Trivy", "Grype"], seenRel: "9h ago", seenAbs: "Jun 12, 03:00", running: true },
    { app: "ipsum", name: "elit-cache", tag: "v1.28.1", registry: "oci.example.io/team", ns: "magna-aliqua", replicas: 3, crit: 6, high: 142, med: 410, low: 30, total: 588, fixable: 365, scanners: ["Trivy", "Grype"], seenRel: "10h ago", seenAbs: "Jun 12, 02:00", running: true },
    { app: "veniam", name: "tempor-proxy", tag: "v2.41.1", registry: "oci.example.io/team", ns: "quis-nostrud", replicas: 1, crit: 0, high: 41, med: 96, low: 12, total: 149, fixable: 0, scanners: ["Trivy", "Grype"], seenRel: "10h ago", seenAbs: "Jun 12, 02:00", running: true },
    { app: "ipsum", name: "labore-queue", tag: "v2.0.0", registry: "oci.example.io/team", ns: "consectetur", replicas: 2, crit: 1, high: 33, med: 88, low: 9, total: 131, fixable: 0, scanners: ["Trivy", "Grype"], seenRel: "10h ago", seenAbs: "Jun 12, 02:00", running: true },
    { app: "ipsum", name: "magna-store", tag: "v0.9.1", registry: "oci.example.io/team", ns: "sed-eiusmod", replicas: 3, crit: 0, high: 28, med: 71, low: 6, total: 105, fixable: 0, scanners: ["Trivy"], seenRel: "11h ago", seenAbs: "Jun 12, 01:00", running: true },
    { app: "elit", name: "aliqua-auth", tag: "v2.9.0", registry: "registry.example.net/lib", ns: "enim-veniam", replicas: 1, crit: 3, high: 61, med: 188, low: 28, total: 280, fixable: 174, scanners: ["Trivy", "Grype"], seenRel: "11h ago", seenAbs: "Jun 12, 01:00", running: true },
    { app: "tempor", name: "veniam-stream", tag: "v8.0.6", registry: "registry.example.net/lib", ns: "tempor-incididunt", replicas: 2, crit: 2, high: 74, med: 233, low: 31, total: 340, fixable: 211, scanners: ["Trivy", "Grype"], seenRel: "12h ago", seenAbs: "Jun 12, 00:00", running: true },
    { app: "ipsum", name: "nostrud-db", tag: "v1.12.1", registry: "registry.example.net/lib", ns: "sed-eiusmod", replicas: 1, crit: 1, high: 22, med: 67, low: 5, total: 95, fixable: 0, scanners: ["Trivy", "Grype"], seenRel: "13h ago", seenAbs: "Jun 11, 23:00", running: true },
    { app: "dolor", name: "consectetur-edge", tag: "v7.0.15", registry: "harbor.example.com/library", ns: "quis-nostrud", replicas: 2, crit: 0, high: 12, med: 41, low: 8, total: 61, fixable: 0, scanners: ["Trivy", "Grype"], seenRel: "14h ago", seenAbs: "Jun 11, 22:00", running: false },
  ];

  // ---- Affected images ----
  const affectedImages = [
    { vuln: "ADV-2025-0019", pkg: "tempor-krb", ptype: "photon", sev: "HIGH", fixed: "1.17-15.ph4", image: "oci.example.io/team/elit-cache:v1.28.1", ns: "magna-aliqua" },
    { vuln: "ADV-2026-0007", pkg: "elit-tls", ptype: "photon", sev: "CRITICAL", fixed: "3.7.10-7.ph4", image: "oci.example.io/team/labore-plugin:v0.12.0", ns: "magna-aliqua" },
    { vuln: "ADV-2026-0011", pkg: "elit-tls", ptype: "photon", sev: "HIGH", fixed: "3.7.10-7.ph4", image: "oci.example.io/team/tempor-proxy:v2.41.1", ns: "quis-nostrud" },
    { vuln: "ADV-2026-0014", pkg: "elit-tls", ptype: "photon", sev: "HIGH", fixed: "3.7.10-7.ph4", image: "oci.example.io/team/labore-queue:v2.0.0", ns: "consectetur" },
    { vuln: "ADV-2026-0019", pkg: "elit-tls", ptype: "photon", sev: "HIGH", fixed: "3.7.10-7.ph4", image: "oci.example.io/team/magna-store:v0.9.1", ns: "sed-eiusmod" },
    { vuln: "ADV-2026-0023", pkg: "elit-tls", ptype: "photon", sev: "CRITICAL", fixed: "3.7.10-7.ph4", image: "registry.example.net/lib/aliqua-auth:v2.9.0", ns: "enim-veniam" },
    { vuln: "ADV-2026-0027", pkg: "elit-tls", ptype: "photon", sev: "HIGH", fixed: "3.7.10-7.ph4", image: "harbor.example.com/library/consectetur-edge:v7.0.15", ns: "quis-nostrud" },
    { vuln: "ADV-2026-0031", pkg: "elit-tls", ptype: "photon", sev: "HIGH", fixed: "3.7.10-7.ph4", image: "registry.example.net/lib/veniam-stream:v8.0.6", ns: "tempor-incididunt" },
  ];

  const L1 = "Lorem ipsum dolor sit amet, consectetur adipiscing elit.";
  const L2 = "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.";
  const L3 = "Ut enim ad minim veniam, quis nostrud exercitation.";

  // ---- Approval list ----
  const approvals = [
    { id: "CVE-2024-20051", sev: "MEDIUM", status: "acknowledged", justification: L1 + " " + L3, impact: "Lorem ipsum dolor sit amet, internal network only.", action: "Monitor for upstream fix; re-evaluate next quarter.", approver: "Amet Consectetur", task: "TASK-1042", when: "May 28, 2026", whenRel: "15d ago" },
    { id: "ADV-2025-0019", sev: "HIGH", status: "resolved", justification: "Lorem ipsum patched in base image rebuild.", impact: L2, action: "Fixed in image rebuild #4412.", approver: "Lorem Ipsum", task: "TASK-1090", when: "May 30, 2026", whenRel: "13d ago" },
    { id: "CVE-2024-10042", sev: "CRITICAL", status: "resolved", justification: "Lorem ipsum upgraded fleet-wide.", impact: L1, action: "Mitigated; scan confirms clean on next sweep.", approver: "Lorem Ipsum", task: "TASK-1001", when: "May 22, 2026", whenRel: "21d ago" },
    { id: "ADV-2026-0007", sev: "CRITICAL", status: "open", justification: "-", impact: "Lorem ipsum cert validation - patch staged.", action: "Awaiting base-image bump to 3.7.10-7.ph4.", approver: "-", task: "TASK-1200", when: "Jun 2, 2026", whenRel: "10d ago" },
    { id: "CVE-2026-30058", sev: "CRITICAL", status: "acknowledged", justification: L2 + " Runtime path not invoked.", impact: "Local path; cluster RBAC mitigates.", action: "Accept risk for 30d, revisit on next sweep.", approver: "Amet Consectetur", task: "TASK-1211", when: "Jun 1, 2026", whenRel: "11d ago" },
  ];

  // ---- Finding detail ----
  const focusFinding = {
    cve: "CVE-2024-10042",
    severity: "CRITICAL",
    title: "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod",
    epss: 0.94, epssPct: 99.2, kev: true, cvss: 9.0,
    cvssVector: "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H",
    cwe: "CWE-22 · Lorem Ipsum",
    pkg: "liblorem", ptype: "debian",
    published: "2024-05-14", discovered: "2026-05-28",
    state: "open", sla: 2, slaDeadline: "May 30, 2026 @ 19:02", overdue: true,
    assignee: { name: "Lorem Ipsum", initials: "LI", tone: "#C0271D" },
    description: L1 + " " + L2 + " " + L3 + " Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
    refs: ["https://advisories.example.com/lorem/CVE-2024-10042", "https://vuln.example.org/detail/CVE-2024-10042"],
    affected: [
      { comp: "lorem-api", ns: "lorem-ipsum", current: "1:2.39.2-1.1", fixed: "1:2.39.5-0+deb12u1", images: 3 },
      { comp: "sit-worker", ns: "adipiscing-elit", current: "1:2.20.1-2+deb10u8", fixed: "1:2.20.1-2+deb10u9", images: 1 },
    ],
    scannerEvidence: [
      { scanner: "Trivy", severity: "CRITICAL", source: "ghsa", fixed: "1:2.39.5-0+deb12u1", vector: "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H", status: "fixed", db: "2026-06-03 02:14" },
      { scanner: "Grype", severity: "CRITICAL", source: "nvd", fixed: "1:2.39.5-0+deb12u1", vector: "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H", status: "fixed", db: "2026-06-03 02:31" },
    ],
  };

  // ---- Contributors (former heroes) ----
  const heroes = [
    { name: "Lorem Ipsum", initials: "LI", role: "Security Lead", tone: "#C0271D", resolved: 412, acknowledged: 88, crit: 41, high: 196, med: 152, low: 23, medianDays: 2.8, slaHit: 94, streak: 19, trend: [6, 8, 7, 11, 9, 14, 12, 16, 13, 18] },
    { name: "Dolor Sit", initials: "DS", role: "Platform / DevOps", tone: "#1F8E84", resolved: 318, acknowledged: 54, crit: 22, high: 141, med: 134, low: 21, medianDays: 3.4, slaHit: 91, streak: 11, trend: [4, 6, 5, 7, 9, 8, 11, 10, 13, 12] },
    { name: "Amet Consectetur", initials: "AC", role: "AppSec Engineer", tone: "#3D7DA6", resolved: 276, acknowledged: 71, crit: 18, high: 118, med: 121, low: 19, medianDays: 3.9, slaHit: 89, streak: 7, trend: [3, 5, 4, 6, 5, 8, 7, 9, 8, 10] },
    { name: "Adipiscing Elit", initials: "AE", role: "SRE", tone: "#7A5BA8", resolved: 184, acknowledged: 33, crit: 9, high: 77, med: 88, low: 10, medianDays: 4.6, slaHit: 84, streak: 4, trend: [2, 3, 4, 3, 5, 4, 6, 5, 7, 6] },
    { name: "Sed Eiusmod", initials: "SE", role: "Backend / ops", tone: "#C2540D", resolved: 142, acknowledged: 26, crit: 6, high: 58, med: 70, low: 8, medianDays: 5.1, slaHit: 82, streak: 3, trend: [1, 2, 3, 2, 4, 3, 4, 5, 4, 5] },
    { name: "Tempor Labore", initials: "TL", role: "Platform / DevOps", tone: "#5C6B77", resolved: 97, acknowledged: 19, crit: 3, high: 39, med: 48, low: 7, medianDays: 5.8, slaHit: 79, streak: 2, trend: [1, 1, 2, 2, 3, 2, 3, 3, 4, 4] },
    { name: "Magna Aliqua", initials: "MA", role: "Security Engineer", tone: "#9A6B05", resolved: 63, acknowledged: 14, crit: 2, high: 24, med: 33, low: 4, medianDays: 6.2, slaHit: 77, streak: 1, trend: [0, 1, 1, 2, 1, 2, 2, 3, 2, 3] },
  ];
  const heroStats = { resolved30d: 1284, acknowledged30d: 305, resolvedWeek: 96, medianDays: 3.6, slaHit: 88, critCleared: 73 };
  const resolvedSeries = {
    days,
    CRITICAL: days.map((_, i) => Math.max(0, Math.round(2 + Math.sin(i * 1.3) * 1.6))),
    HIGH: days.map((_, i) => Math.max(0, Math.round(9 + Math.sin(i * 0.9) * 5))),
    MEDIUM: days.map((_, i) => Math.max(0, Math.round(18 + Math.sin(i * 1.1) * 9))),
    LOW: days.map((_, i) => Math.max(0, Math.round(5 + Math.sin(i * 1.7) * 3))),
  };
  const activity = [
    { who: "Lorem Ipsum", initials: "LI", tone: "#C0271D", act: "resolved", cve: "ADV-2025-0019", sev: "HIGH", note: "Lorem ipsum patched in base image rebuild", when: "12m ago" },
    { who: "Dolor Sit", initials: "DS", tone: "#1F8E84", act: "acknowledged", cve: "CVE-2026-30058", sev: "CRITICAL", note: "Runtime path not invoked; accept 30d", when: "48m ago" },
    { who: "Amet Consectetur", initials: "AC", tone: "#3D7DA6", act: "resolved", cve: "CVE-2025-20217", sev: "CRITICAL", note: "Lorem ipsum bumped fleet-wide", when: "1h ago" },
    { who: "Lorem Ipsum", initials: "LI", tone: "#C0271D", act: "resolved", cve: "CVE-2024-10042", sev: "CRITICAL", note: "Confirmed clean on next sweep", when: "3h ago" },
    { who: "Adipiscing Elit", initials: "AE", tone: "#7A5BA8", act: "opened", cve: "ADV-2026-0007", sev: "CRITICAL", note: "Patch staged, awaiting base bump", when: "4h ago" },
    { who: "Sed Eiusmod", initials: "SE", tone: "#C2540D", act: "resolved", cve: "CVE-2024-10077", sev: "CRITICAL", note: "Lorem ipsum rebuild on photon base", when: "5h ago" },
    { who: "Amet Consectetur", initials: "AC", tone: "#3D7DA6", act: "acknowledged", cve: "CVE-2024-20051", sev: "MEDIUM", note: "Third-party component, no fix available", when: "yesterday" },
    { who: "Dolor Sit", initials: "DS", tone: "#1F8E84", act: "resolved", cve: "CVE-2025-20013", sev: "CRITICAL", note: "Lorem ipsum 2.68.4-7.ph4", when: "yesterday" },
  ];

  const clusters = [
    { id: "id-lorem-9c2e", name: "lorem-prod", current: true, crit: 119, high: 1793, med: 4396, low: 467, images: 13, replicas: 27, sweepRel: "5h ago", sweepAbs: "Jun 12, 07:00", health: "healthy", scannerHealth: { Trivy: "ok", Grype: "ok" } },
    { id: "id-ipsum-44ad", name: "ipsum-staging", current: false, crit: 38, high: 512, med: 1204, low: 188, images: 9, replicas: 14, sweepRel: "6h ago", sweepAbs: "Jun 12, 06:00", health: "degraded", scannerHealth: { Trivy: "ok", Grype: "failing" } },
    { id: "id-dolor-71bb", name: "dolor-sandbox", current: false, crit: 7, high: 101, med: 355, low: 61, images: 5, replicas: 6, sweepRel: "3d ago", sweepAbs: "Jun 9, 07:00", health: "stale", scannerHealth: { Trivy: "ok", Grype: "ok" } },
    { id: "id-amet-08fe", name: "amet-fresh", current: false, firstRun: true, crit: 0, high: 0, med: 0, low: 0, images: 0, replicas: 0, sweepRel: "pending", sweepAbs: "First sweep scheduled 07:00", health: "pending", scannerHealth: {} },
  ];

  // ---- Settings / scanner configuration ----
  const config = {
    scanScope: {
      runningOnly: true,
      includeActive: false,
      includeNamespaces: ["lorem-ipsum", "dolor-sit-amet"],
      ignoreActive: true,
      ignoreNamespaces: ["dolor-sandbox", "ipsum-staging", "kube-system"],
      excludeImagePatterns: ["*/lorem-base:*", "registry.example.com/group/test-*"],
      excludeKinds: ["Job", "CronJob"],
    },
    trivy: { enabled: true, version: "0.55.2 (latest)", severities: ["CRITICAL", "HIGH", "MEDIUM", "LOW"], ignoreUnfixed: false, pkgTypes: ["os", "library"], scanScopeLayers: "squashed", timeout: 10, concurrency: 3 },
    grype: { enabled: true, version: "0.84.0 (latest)", failOn: "high", onlyFixed: false, scope: "squashed", checkAppUpdate: false },
    schedule: { interval: "6h", sweepTime: "07:00", staleWindow: "1.5x", backoff: true },
    sla: { CRITICAL: 2, HIGH: 7, MEDIUM: 30, LOW: 90, kevOverride: true, kevHours: 24 },
    ignoreRules: [
      { id: "CVE-2024-20051", scope: "liblorem", reason: "Lorem ipsum, no fix available - mitigated by network policy.", by: "Amet Consectetur", expires: "2026-09-15" },
      { id: "CVE-2024-10310", scope: "all images", reason: "False positive, not exploitable in our configuration.", by: "Lorem Ipsum", expires: "2026-07-30" },
      { id: "ADV-2025-0019", scope: "dolor-svc", reason: "Tracked in TASK-1090, fix scheduled next release.", by: "Dolor Sit", expires: "2026-08-01" },
    ],
    vulnDb: {
      cacheVolume: "/var/cache/javv-db (20Gi PVC)",
      trivy: {
        dbRepository: "registry.example.com/group/trivy-db",
        javaDbRepository: "registry.example.com/group/trivy-java-db",
        refresh: "12h",
        skipUpdate: false,
        builtRel: "10h ago",
        builtAbs: "Jun 12, 02:14",
      },
      grype: {
        updateUrl: "https://registry.example.com/grype/databases/listing.json",
        caCert: "/etc/ssl/certs/grype-mirror-ca.crt",
        autoUpdate: true,
        maxBuiltAge: "120h",
        validateAge: true,
        builtRel: "9h ago",
        builtAbs: "Jun 12, 02:31",
      },
    },
    versions: {
      trivy: ["0.55.2 (latest)", "0.55.0", "0.54.1", "0.53.0"],
      grype: ["0.84.0 (latest)", "0.83.2", "0.82.2", "0.80.1"],
    },
    access: {
      httpsOnly: true,
      pushTokens: [
        { scanner: "Trivy", token: "javv_push_••••••••••••8c2d", scope: "push:findings", created: "May 2, 2026", lastUsed: "5h ago", lastUsedAbs: "Jun 12, 07:01" },
        { scanner: "Grype", token: "javv_push_••••••••••••41f7", scope: "push:findings", created: "May 2, 2026", lastUsed: "5h ago", lastUsedAbs: "Jun 12, 07:03" },
      ],
      autoResolveSecrets: true,
      registries: ["registry.example.com", "oci.example.io", "harbor.example.com"],
    },
  };

  // ---- Notifications (assigned + SLA breaches for current user) ----
  const notifications = [
    { type: "sla", cve: "CVE-2024-10042", sev: "CRITICAL", msg: "SLA overdue - assigned to you", rel: "2h ago", abs: "Jun 12, 10:04" },
    { type: "assigned", cve: "ADV-2026-0007", sev: "CRITICAL", msg: "Dolor Sit assigned this to you", rel: "6h ago", abs: "Jun 12, 06:31" },
    { type: "assigned", cve: "CVE-2025-20119", sev: "HIGH", msg: "New finding assigned to you", rel: "1d ago", abs: "Jun 11, 09:12" },
  ];

  // ---- Saved views (named filter sets) ----
  const savedViews = [
    { name: "KEV criticals", desc: "Known-exploited criticals - patch first", owner: "Lorem Ipsum", filters: { severity: ["CRITICAL"], attr: ["kev"] } },
    { name: "Unassigned highs", desc: "High severity with no owner yet", owner: "Dolor Sit", filters: { severity: ["HIGH"], assignee: ["Unassigned"] } },
    { name: "Scanner disagreements", desc: "Trivy and Grype rate these differently", owner: "Amet Consectetur", filters: { attr: ["disagree"] } },
    { name: "Gone stale", desc: "Findings that stopped arriving from the sweep", owner: "Lorem Ipsum", filters: { state: ["stale"] } },
    { name: "Fixable criticals", desc: "Critical + fix available - quick wins", owner: "Sed Eiusmod", filters: { severity: ["CRITICAL"], attr: ["hasfix"] } },
  ];

  // ---- User audit log (who did what) ----
  const auditLog = [
    { user: "Lorem Ipsum", initials: "LI", tone: "#C0271D", action: "resolved", target: "ADV-2025-0019", sev: "HIGH", detail: "Patched in base image rebuild #4412", task: "TASK-1090", rel: "12m ago", abs: "Jun 12, 11:54" },
    { user: "Dolor Sit", initials: "DS", tone: "#1F8E84", action: "acknowledged", target: "CVE-2026-30058", sev: "CRITICAL", detail: "Runtime path not invoked; risk accepted 30d", task: "TASK-1211", rel: "48m ago", abs: "Jun 12, 11:18" },
    { user: "Amet Consectetur", initials: "AC", tone: "#3D7DA6", action: "assigned", target: "CVE-2025-20119", sev: "HIGH", detail: "Assigned to Sed Eiusmod", task: "TASK-1284", rel: "1h ago", abs: "Jun 12, 10:51" },
    { user: "Lorem Ipsum", initials: "LI", tone: "#C0271D", action: "resolved", target: "CVE-2024-10042", sev: "CRITICAL", detail: "Confirmed clean on next sweep", task: "TASK-1001", rel: "3h ago", abs: "Jun 12, 09:02" },
    { user: "Adipiscing Elit", initials: "AE", tone: "#7A5BA8", action: "ignore-rule", target: "CVE-2024-10310", sev: "MEDIUM", detail: "Added ignore rule · false positive · expires 2026-07-30", task: "TASK-1102", rel: "4h ago", abs: "Jun 12, 08:13" },
    { user: "Sed Eiusmod", initials: "SE", tone: "#C2540D", action: "resolved", target: "CVE-2024-10077", sev: "CRITICAL", detail: "Rebuild on photon base", task: "TASK-1066", rel: "5h ago", abs: "Jun 12, 07:09" },
    { user: "Lorem Ipsum", initials: "LI", tone: "#C0271D", action: "config", target: "Settings · Schedule", sev: null, detail: "Scan interval 12h → 6h", task: null, rel: "8h ago", abs: "Jun 12, 04:00" },
    { user: "Amet Consectetur", initials: "AC", tone: "#3D7DA6", action: "acknowledged", target: "CVE-2024-20051", sev: "MEDIUM", detail: "Third-party component, no fix available", task: "TASK-1042", rel: "1d ago", abs: "Jun 11, 09:40" },
    { user: "Dolor Sit", initials: "DS", tone: "#1F8E84", action: "resolved", target: "CVE-2025-20013", sev: "CRITICAL", detail: "Lorem ipsum 2.68.4-7.ph4", task: "TASK-1207", rel: "1d ago", abs: "Jun 11, 08:22" },
    { user: "Adipiscing Elit", initials: "AE", tone: "#7A5BA8", action: "assigned", target: "ADV-2026-0007", sev: "CRITICAL", detail: "Assigned to Lorem Ipsum", task: "TASK-1200", rel: "1d ago", abs: "Jun 11, 07:55" },
    { user: "Magna Aliqua", initials: "MA", tone: "#9A6B05", action: "export", target: "Findings CSV", sev: null, detail: "1,204 rows · severity ≥ HIGH", task: null, rel: "2d ago", abs: "Jun 10, 15:31" },
    { user: "Lorem Ipsum", initials: "LI", tone: "#C0271D", action: "config", target: "Settings · Scanners", sev: null, detail: "Trivy 0.54.1 → 0.55.2", task: null, rel: "2d ago", abs: "Jun 10, 09:12" },
    { user: "Tempor Labore", initials: "TL", tone: "#5C6B77", action: "reassigned", target: "CVE-2025-20217", sev: "CRITICAL", detail: "Sed Eiusmod → Amet Consectetur", task: "TASK-1233", rel: "3d ago", abs: "Jun 9, 14:06" },
    { user: "Dolor Sit", initials: "DS", tone: "#1F8E84", action: "ignore-rule", target: "ADV-2025-0019", sev: "HIGH", detail: "Added ignore rule · expires 2026-08-01", task: "TASK-1090", rel: "4d ago", abs: "Jun 8, 11:47" },
    { user: "Sed Eiusmod", initials: "SE", tone: "#C2540D", action: "token", target: "Push token · Grype", sev: null, detail: "Rotated API access token", task: null, rel: "5d ago", abs: "Jun 7, 10:02" },
  ];

  // ---- Scanner / ingest pipeline status ----
  const scannerStatus = [
    { name: "Trivy", version: "0.55.2", health: "ok", lastRunRel: "5h ago", lastRunAbs: "Jun 12, 07:00", ingested24h: 412, failed24h: 3, queue: 0, dbRel: "10h ago", dbAbs: "Jun 12, 02:14" },
    { name: "Grype", version: "0.84.0", health: "degraded", lastRunRel: "5h ago", lastRunAbs: "Jun 12, 07:03", ingested24h: 405, failed24h: 11, queue: 2, dbRel: "9h ago", dbAbs: "Jun 12, 02:31" },
  ];
  const ingestSeries = {
    days,
    Trivy: days.map((_, i) => Math.round(400 + Math.sin(i * 1.1) * 24 + (i > 26 ? -6 : 0))),
    Grype: days.map((_, i) => Math.round(392 + Math.sin(i * 0.9 + 1) * 26 - (i > 24 ? 28 : 0))),
  };
  const failedSeries = {
    days,
    Trivy: days.map((_, i) => ({ 4: 6, 13: 3, 22: 2 }[i] || (Math.abs(Math.sin(i * 2.1)) > 0.93 ? 2 : 0))),
    Grype: days.map((_, i) => ({ 25: 9, 26: 14, 27: 8, 28: 11, 29: 11 }[i] || (Math.abs(Math.sin(i * 1.7)) > 0.9 ? 3 : 1))),
  };
  const failedIngest = [
    { rel: "4h ago", abs: "Jun 12, 08:02", scanner: "Grype", image: "registry.example.com/group/lorem-api:v1.4.0", stage: "parse", error: "schema_version mismatch (2 ≠ 3)", retries: 3, status: "dead-letter" },
    { rel: "5h ago", abs: "Jun 12, 07:04", scanner: "Grype", image: "registry.example.com/group/ipsum-web:v4.8.1", stage: "push", error: "401 - API token expired", retries: 5, status: "retrying" },
    { rel: "5h ago", abs: "Jun 12, 07:02", scanner: "Trivy", image: "registry.example.com/group/sit-worker:v1.1.2", stage: "scan", error: "timeout after 10m", retries: 1, status: "retrying" },
    { rel: "11h ago", abs: "Jun 12, 01:11", scanner: "Grype", image: "oci.example.io/team/elit-cache:v1.28.1", stage: "push", error: "413 - payload exceeds 25MB cap", retries: 4, status: "dead-letter" },
    { rel: "1d ago", abs: "Jun 11, 07:01", scanner: "Grype", image: "harbor.example.com/library/consectetur-edge:v7.0.15", stage: "pull", error: "manifest unknown - tag deleted upstream", retries: 2, status: "dead-letter" },
    { rel: "1d ago", abs: "Jun 11, 06:58", scanner: "Trivy", image: "registry.example.net/lib/aliqua-auth:v2.9.0", stage: "scan", error: "vuln DB corrupt - cache evicted, refetching", retries: 1, status: "resolved" },
  ];

  // ---- RBAC ----
  const rbac = {
    roles: ["Viewer", "Auditor", "Operator", "Security Lead", "Admin"],
    permissions: [
      { perm: "View dashboards & findings", grants: [1, 1, 1, 1, 1] },
      { perm: "View audit log", grants: [0, 1, 1, 1, 1] },
      { perm: "Export CSV", grants: [0, 1, 1, 1, 1] },
      { perm: "Acknowledge & assign", grants: [0, 0, 1, 1, 1] },
      { perm: "Resolve findings", grants: [0, 0, 1, 1, 1] },
      { perm: "Approve exceptions", grants: [0, 0, 0, 1, 1] },
      { perm: "Manage ignore rules & SLA", grants: [0, 0, 0, 1, 1] },
      { perm: "Edit scanner settings", grants: [0, 0, 0, 0, 1] },
      { perm: "Manage users & tokens", grants: [0, 0, 0, 0, 1] },
    ],
    users: [
      { name: "Lorem Ipsum", initials: "LI", tone: "#C0271D", role: "Security Lead", lastActive: "12m ago", lastActiveAbs: "Jun 12, 11:54" },
      { name: "Dolor Sit", initials: "DS", tone: "#1F8E84", role: "Operator", lastActive: "48m ago", lastActiveAbs: "Jun 12, 11:18" },
      { name: "Amet Consectetur", initials: "AC", tone: "#3D7DA6", role: "Operator", lastActive: "1h ago", lastActiveAbs: "Jun 12, 10:51" },
      { name: "Adipiscing Elit", initials: "AE", tone: "#7A5BA8", role: "Viewer", lastActive: "4h ago", lastActiveAbs: "Jun 12, 08:13" },
      { name: "Magna Aliqua", initials: "MA", tone: "#9A6B05", role: "Auditor", lastActive: "2d ago", lastActiveAbs: "Jun 10, 15:31" },
    ],
  };

  window.JAVV = {
    SEV, severityTotals, new30d, namespaces, applications, packageTypes,
    languageBinaries, topComponents, severitySeries, publishedSeries,
    findings, images, affectedImages, approvals, focusFinding, clusters,
    heroes, heroStats, resolvedSeries, activity, config, notifications, savedViews, auditLog,
    scannerStatus, ingestSeries, failedSeries, failedIngest, rbac,
  };
})();
