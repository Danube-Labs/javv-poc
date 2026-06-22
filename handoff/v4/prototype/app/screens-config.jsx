/* JAVV — Settings / scanner & app configuration */
function Toggle({ on, onChange }) {
  return <button className={"switch " + (on ? "switch-on" : "")} onClick={() => onChange(!on)} role="switch" aria-checked={on}><i /></button>;
}
function Seg({ value, options, onChange }) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.v} className={"seg-opt " + (value === o.v ? "seg-on" : "")} onClick={() => onChange(o.v)}>{o.label}</button>
      ))}
    </div>
  );
}
function Chips({ items, onRemove, onAdd, placeholder }) {
  const [val, setVal] = useState("");
  const add = () => { const v = val.trim(); if (v) { onAdd(v); setVal(""); } };
  return (
    <div className="chips">
      {items.map((c) => (
        <span className="chip" key={c}>{c}<button onClick={() => onRemove(c)} aria-label="remove">×</button></span>
      ))}
      <input className="chip-input mono-cell" value={val} placeholder={placeholder} onChange={(e) => setVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
    </div>
  );
}
function Row({ label, hint, children, stack }) {
  return (
    <div className={"set-row " + (stack ? "set-row-stack" : "")}>
      <div className="set-row-label"><span>{label}</span>{hint && <span className="set-hint">{hint}</span>}</div>
      <div className="set-row-ctrl">{children}</div>
    </div>
  );
}
function Check({ on, onChange, children }) {
  return (
    <button className={"checkbox-row " + (on ? "checkbox-on" : "")} onClick={() => onChange(!on)}>
      <span className="cb-box" />{children}
    </button>
  );
}

/* Reusable save/discard footer — appended to the end of every settings category. */
function SaveBar({ dirty, onSave, onDiscard }) {
  return (
    <div className={"save-bar " + (dirty ? "save-bar-on" : "")}>
      <span className="save-msg">{dirty ? "You have unsaved changes" : "All changes saved"}</span>
      <div className="save-actions">
        <button className="btn btn-ghost" disabled={!dirty} onClick={onDiscard}>Discard</button>
        <button className="btn btn-primary" disabled={!dirty} onClick={onSave}>Save changes</button>
      </div>
    </div>
  );
}

function Settings({ go }) {
  const cfg = JAVV.config;
  const sections = [
    ["scope", "Scan scope", "filter", "cluster"],
    ["scanners", "Scanners", "shield", "scanner"],
    ["schedule", "Schedule", "clock", "cluster"],
    ["sla", "SLA policy", "alert", "org"],
    ["ignore", "Ignore rules", "check", "cluster"],
    ["db", "Vulnerability DB", "layers", "scanner"],
    ["access", "Access & registries", "cube", "cluster"],
    ["data", "Data & OpenSearch", "database", "cluster"],
    ["users", "Users & roles", "users", "org"],
    ["cluster", "Cluster", "gear", "cluster"],
  ];
  const SCOPE = {
    cluster: { label: "Per cluster", cls: "scope-cluster", note: "Applies to lorem-prod only. Other clusters keep their own settings." },
    scanner: { label: "Per scanner", cls: "scope-scanner", note: "Configured independently for each scanner (Trivy and Grype)." },
    org: { label: "Organization", cls: "scope-org", note: "Shared across every cluster and user in the organization." },
  };
  const [sec, setSec] = useState("scope");
  const [dbScanner, setDbScanner] = useState("trivy");
  const [dirty, setDirty] = useState(false);
  const [s, setS] = useState(() => JSON.parse(JSON.stringify(cfg)));
  const touch = () => setDirty(true);
  const set = (path, val) => { setS((prev) => { const n = JSON.parse(JSON.stringify(prev)); let o = n; const ks = path.split("."); for (let i = 0; i < ks.length - 1; i++) o = o[ks[i]]; o[ks[ks.length - 1]] = val; return n; }); touch(); };
  const toggleIn = (arr, v) => arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];

  const SEVS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];

  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Settings</h1>
          <p className="screen-sub">Configuration for <b>lorem-prod</b> · each section notes whether it applies per cluster, per scanner, or organization-wide</p>
        </div>
      </div>

      <div className="set-layout">
        <aside className="set-nav">
          {sections.map(([k, label, icon, scope]) => (
            <button key={k} className={"set-nav-item " + (sec === k ? "set-nav-on" : "")} onClick={() => setSec(k)}>
              <Icon name={icon} size={15} /><span>{label}</span>
              <i className={"scope-dot " + SCOPE[scope].cls} title={SCOPE[scope].label} />
            </button>
          ))}
        </aside>

        <div className="set-panel">
          <div className="set-panel-body">
          {(() => { const sc = SCOPE[(sections.find((x) => x[0] === sec) || [])[3]]; return sc ? (
            <div className={"scope-strip " + sc.cls}><span className="scope-badge">{sc.label}</span><span className="scope-note">{sc.note}</span></div>
          ) : null; })()}
          {sec === "scope" && (
            <Card title="Scan scope" subtitle="what the scanner module discovers and scans">
              <Row label="Running workloads only" hint="Discover live images from the k8s API, digest-deduped — not a registry crawl.">
                <Toggle on={s.scanScope.runningOnly} onChange={(v) => set("scanScope.runningOnly", v)} />
              </Row>
              <Row label="Namespace include list" hint="When active, only namespaces in the list below are scanned.">
                <Toggle on={s.scanScope.includeActive} onChange={(v) => set("scanScope.includeActive", v)} />
              </Row>
              {s.scanScope.includeActive && (
                <Row label="Included namespaces" stack hint="Type a namespace and press Enter. Matches the k8s namespace name.">
                  <Chips placeholder="add namespace…"
                    items={s.scanScope.includeNamespaces}
                    onAdd={(v) => set("scanScope.includeNamespaces", [...s.scanScope.includeNamespaces, v])}
                    onRemove={(v) => set("scanScope.includeNamespaces", s.scanScope.includeNamespaces.filter((x) => x !== v))} />
                </Row>
              )}
              <Row label="Namespace ignore list" hint="When active, namespaces in the list below are skipped by the scanner.">
                <Toggle on={s.scanScope.ignoreActive} onChange={(v) => set("scanScope.ignoreActive", v)} />
              </Row>
              {s.scanScope.ignoreActive && (
                <Row label="Ignored namespaces" stack hint="Type a namespace and press Enter. Matches the k8s namespace name.">
                  <Chips placeholder="add namespace…"
                    items={s.scanScope.ignoreNamespaces}
                    onAdd={(v) => set("scanScope.ignoreNamespaces", [...s.scanScope.ignoreNamespaces, v])}
                    onRemove={(v) => set("scanScope.ignoreNamespaces", s.scanScope.ignoreNamespaces.filter((x) => x !== v))} />
                </Row>
              )}
              {s.scanScope.includeActive && s.scanScope.ignoreActive && (
                <div className="ignore-best" style={{ marginTop: 12, marginBottom: 0 }}><Icon name="layers" size={13} />Both lists active: the include list is applied first, then ignored namespaces are subtracted from it.</div>
              )}
              <Row label="Excluded image patterns" stack hint="Glob patterns against the full image reference.">
                <Chips placeholder="*/base-image:*" items={s.scanScope.excludeImagePatterns}
                  onAdd={(v) => set("scanScope.excludeImagePatterns", [...s.scanScope.excludeImagePatterns, v])}
                  onRemove={(v) => set("scanScope.excludeImagePatterns", s.scanScope.excludeImagePatterns.filter((x) => x !== v))} />
              </Row>
              <Row label="Skip workload kinds" stack hint="Ephemeral kinds you don't want inventoried.">
                <Chips placeholder="Job, CronJob…" items={s.scanScope.excludeKinds}
                  onAdd={(v) => set("scanScope.excludeKinds", [...s.scanScope.excludeKinds, v])}
                  onRemove={(v) => set("scanScope.excludeKinds", s.scanScope.excludeKinds.filter((x) => x !== v))} />
              </Row>
            </Card>
          )}

          {sec === "scanners" && (
            <div className="stack">
              <div className="scanner-banner"><Icon name="layers" size={14} />Both scanners run from day one, each with its own settings below. Results are kept <b>per-scanner</b> and never merged — dashboards facet by scanner to avoid double-counting.</div>

              <Card title={<span className="set-card-title"><ScannerTag name="Trivy" /> Trivy</span>} subtitle="Aqua Security · OS + language packages">
                <Row label="Enabled"><Toggle on={s.trivy.enabled} onChange={(v) => set("trivy.enabled", v)} /></Row>
                <Row label="Scanner version" hint="Rolled out by the scanner module on the next cycle.">
                  <select className="select-input mono-cell" value={s.trivy.version} onChange={(e) => set("trivy.version", e.target.value)}>
                    {JAVV.config.versions.trivy.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                </Row>
                <Row label="Report severities" stack hint="Which severities the scanner reports.">
                  <div className="check-grid">
                    {SEVS.map((sv) => <Check key={sv} on={s.trivy.severities.includes(sv)} onChange={() => set("trivy.severities", toggleIn(s.trivy.severities, sv))}><Sev level={sv} dot={false} /></Check>)}
                  </div>
                </Row>
                <Row label="Ignore unfixed" hint="Hides CVEs with no fix. Use with a patching plan — it can mask real risk.">
                  <Toggle on={s.trivy.ignoreUnfixed} onChange={(v) => set("trivy.ignoreUnfixed", v)} />
                </Row>
                <Row label="Package types" stack hint="--pkg-types">
                  <div className="check-grid">
                    {["os", "library"].map((t) => <Check key={t} on={s.trivy.pkgTypes.includes(t)} onChange={() => set("trivy.pkgTypes", toggleIn(s.trivy.pkgTypes, t))}><span className="mono-cell">{t}</span></Check>)}
                  </div>
                </Row>
                <Row label="Layer scope">
                  <Seg value={s.trivy.scanScopeLayers} onChange={(v) => set("trivy.scanScopeLayers", v)} options={[{ v: "squashed", label: "Squashed" }, { v: "all-layers", label: "All layers" }]} />
                </Row>
                <div className="set-row-2col">
                  <Row label="Timeout (min)"><input className="num-input mono-cell" type="number" value={s.trivy.timeout} onChange={(e) => set("trivy.timeout", +e.target.value)} /></Row>
                  <Row label="Concurrency"><input className="num-input mono-cell" type="number" value={s.trivy.concurrency} onChange={(e) => set("trivy.concurrency", +e.target.value)} /></Row>
                </div>
              </Card>

              <Card title={<span className="set-card-title"><ScannerTag name="Grype" /> Grype</span>} subtitle="Anchore · independent DB coverage">
                <Row label="Enabled"><Toggle on={s.grype.enabled} onChange={(v) => set("grype.enabled", v)} /></Row>
                <Row label="Scanner version" hint="Rolled out by the scanner module on the next cycle.">
                  <select className="select-input mono-cell" value={s.grype.version} onChange={(e) => set("grype.version", e.target.value)}>
                    {JAVV.config.versions.grype.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                </Row>
                <Row label="Fail-on severity" hint="--fail-on · floor for flagging the scan run.">
                  <Seg value={s.grype.failOn} onChange={(v) => set("grype.failOn", v)} options={[{ v: "critical", label: "Critical" }, { v: "high", label: "High" }, { v: "medium", label: "Medium" }]} />
                </Row>
                <Row label="Only fixed" hint="--only-fixed · report only CVEs with an available fix.">
                  <Toggle on={s.grype.onlyFixed} onChange={(v) => set("grype.onlyFixed", v)} />
                </Row>
                <Row label="Scope">
                  <Seg value={s.grype.scope} onChange={(v) => set("grype.scope", v)} options={[{ v: "squashed", label: "Squashed" }, { v: "all-layers", label: "All layers" }]} />
                </Row>
                <Row label="Check for app update" hint="Phone home for new Grype releases."><Toggle on={s.grype.checkAppUpdate} onChange={(v) => set("grype.checkAppUpdate", v)} /></Row>
              </Card>
            </div>
          )}

          {sec === "schedule" && (
            <Card title="Schedule" subtitle="scan cadence, staleness sweep & delivery">
              <Row label="Scan interval" hint="How often the scanner module re-scans running images.">
                <Seg value={s.schedule.interval} onChange={(v) => set("schedule.interval", v)} options={[{ v: "3h", label: "3h" }, { v: "6h", label: "6h" }, { v: "12h", label: "12h" }, { v: "24h", label: "24h" }]} />
              </Row>
              <Row label="Daily sweep time" hint="When the staleness sweep runs (cluster local time).">
                <input className="num-input mono-cell" type="time" value={s.schedule.sweepTime} onChange={(e) => set("schedule.sweepTime", e.target.value)} style={{ width: 120 }} />
              </Row>
              <Row label="Staleness window" hint="Findings not re-pushed within this multiple of the cadence flip to stale. Resolve stays manual.">
                <Seg value={s.schedule.staleWindow} onChange={(v) => set("schedule.staleWindow", v)} options={[{ v: "1x", label: "1× cadence" }, { v: "1.5x", label: "1.5×" }, { v: "2x", label: "2×" }]} />
              </Row>
              <Row label="Retry with backoff + jitter" hint="Per-image push retried, dead-letter on permanent failure. Ingest is idempotent.">
                <Toggle on={s.schedule.backoff} onChange={(v) => set("schedule.backoff", v)} />
              </Row>
            </Card>
          )}

          {sec === "sla" && (
            <Card title="SLA policy" subtitle="remediation deadlines per severity — drives the SLA column and overdue flags">
              {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((sv) => (
                <Row key={sv} label={<Sev level={sv} />} hint={sv === "CRITICAL" ? "Clock starts when the finding first appears in a sweep." : null}>
                  <div className="sla-input">
                    <input className="num-input mono-cell" type="number" min="1" value={s.sla[sv]} onChange={(e) => set("sla." + sv, +e.target.value)} />
                    <span className="sla-unit">days</span>
                  </div>
                </Row>
              ))}
              <Row label="KEV override" hint="Known-exploited findings ignore the table above and get a tighter deadline.">
                <div className="sla-input">
                  <Toggle on={s.sla.kevOverride} onChange={(v) => set("sla.kevOverride", v)} />
                  {s.sla.kevOverride && <><input className="num-input mono-cell" type="number" min="1" value={s.sla.kevHours} onChange={(e) => set("sla.kevHours", +e.target.value)} /><span className="sla-unit">hours</span></>}
                </div>
              </Row>
              <div className="ignore-best" style={{ marginTop: 14, marginBottom: 0 }}><Icon name="check" size={13} />Editable by Security Lead and Admin roles only. Changes apply to new findings; existing deadlines are not rewritten.</div>
            </Card>
          )}

          {sec === "data" && (() => {
            const d = JAVV.dataOps;
            const canManage = can("can_manage_retention");
            return (
            <div className="stack">
              <div className="scanner-banner"><Icon name="database" size={14} />JAVV drives the OpenSearch ISM policies from here. {canManage ? "" : "Read-only — you don't hold can_manage_retention."}</div>
              <Card title="Retention" subtitle="how far back each index can be read — per cluster · independent per purpose">
                {[["occurrences", "Point-in-time occurrences", "exact CVE-level history — the main cost lever"], ["scanEvents", "Scan events", "trend charts"], ["auditLog", "Audit log", "who-did-what + Contributors window — kept long"], ["images", "Inventory snapshots", "running-images history"]].map(([k, label, note]) => (
                  <Row key={k} label={label} hint={note}>
                    <div className="ret-input"><input className="num-input mono-cell" type="number" defaultValue={d.retentionDays[k]} disabled={!canManage} onChange={touch} /><span className="ret-unit">days</span></div>
                  </Row>
                ))}
              </Card>
              <Card title="Rollover thresholds" subtitle="when a write index rolls to a new one (whichever trips first)">
                <div className="set-row-2col">
                  <Row label="Max docs"><input className="num-input mono-cell" defaultValue={d.rollover.maxDocs} disabled={!canManage} onChange={touch} /></Row>
                  <Row label="Max age"><input className="num-input mono-cell" defaultValue={d.rollover.maxAge} disabled={!canManage} onChange={touch} /></Row>
                </div>
                <Row label="Max primary size"><input className="num-input mono-cell" defaultValue={d.rollover.maxSize} disabled={!canManage} onChange={touch} /></Row>
              </Card>
              <Card title="Snapshots" subtitle="native OpenSearch snapshot/restore"
                action={<span className={"health-chip h-" + d.snapshot.status}><i />last {d.snapshot.last}</span>}>
                <Row label="Repository" stack><input className="text-input mono-cell" defaultValue={d.snapshot.repo} disabled={!canManage} onChange={touch} /></Row>
                <div className="set-row-2col">
                  <Row label="Schedule"><input className="text-input" defaultValue={d.snapshot.schedule} disabled={!canManage} onChange={touch} /></Row>
                  <Row label="Snapshots retained"><input className="num-input mono-cell" defaultValue={d.snapshot.retained} disabled={!canManage} onChange={touch} /></Row>
                </div>
                <Row label="Manual" hint="Restore is destructive — Admins only, and journaled.">
                  <div className="snap-actions">
                    <Gate cap="can_restore_snapshot" disable><button className="btn btn-mini" disabled={!can("can_restore_snapshot")}>Snapshot now</button></Gate>
                    <Gate cap="can_restore_snapshot" disable reason="Restore needs can_restore_snapshot"><button className="btn btn-mini btn-danger" disabled={!can("can_restore_snapshot")}>Restore…</button></Gate>
                  </div>
                </Row>
              </Card>
              <Card title="Staleness timers" subtitle="two-timer model — drives the stale state & inventory banners">
                <div className="set-row-2col">
                  <Row label="Per-finding freshness" hint="Not re-seen within this → stale."><div className="ret-input"><input className="num-input mono-cell" defaultValue={d.staleness.freshnessDays} disabled={!canManage} onChange={touch} /><span className="ret-unit">days</span></div></Row>
                  <Row label="Scanner-down escalation" hint="Scanner silent this long → stale all its findings."><div className="ret-input"><input className="num-input mono-cell" defaultValue={d.staleness.scannerDownDays} disabled={!canManage} onChange={touch} /><span className="ret-unit">days</span></div></Row>
                </div>
                <p className="evidence-note">Between the two thresholds the per-finding timer is <b>held</b> (a brief outage won't mass-stale everything) — inventory shows a "scanner silent" banner instead.</p>
              </Card>
            </div>
            );
          })()}

          {sec === "users" && (
            <div className="stack">
              <div className="scanner-banner"><Icon name="users" size={14} />A role is a <b>bundle of capabilities</b>. Endpoints check the capability (e.g. <span className="mono-cell">can_accept_audit_final</span>), never the role name — so the UI and the server agree.</div>
              <Card title="Users" subtitle="role is granted per user — enforced on every API call, not just hidden in the UI"
                action={<Gate cap="can_manage_users" disable><button className="btn btn-mini" disabled={!can("can_manage_users")}><Icon name="plus" size={13} />Invite user</button></Gate>}>
                <table className="tbl">
                  <thead><tr><th>User</th><th>Role</th><th>Last active</th><th></th></tr></thead>
                  <tbody>
                    {JAVV.rbac.users.map((u) => (
                      <tr key={u.name}>
                        <td><span className="assignee-cell"><Avatar initials={u.initials} tone={u.tone} size={26} />{u.name}</span></td>
                        <td>
                          <select className="select-input" defaultValue={u.role} onChange={touch} style={{ minWidth: 140 }}>
                            {JAVV.rbac.roles.map((r) => <option key={r} value={r}>{r}</option>)}
                          </select>
                        </td>
                        <td><RelTime rel={u.lastActive} abs={u.lastActiveAbs} /></td>
                        <td className="c"><button className="icon-del" title="Remove user"><Icon name="trash" size={14} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
              <Card title="Role permissions" subtitle="what each role can do">
                <table className="tbl tbl-bordered role-matrix">
                  <thead><tr><th>Permission</th>{JAVV.rbac.roles.map((r) => <th key={r} className="c">{r}</th>)}</tr></thead>
                  <tbody>
                    {JAVV.rbac.permissions.map((p) => (
                      <tr key={p.perm}>
                        <td>{p.perm}</td>
                        {p.grants.map((g, i) => (
                          <td key={i} className="c">{g ? <span className="perm-yes"><Icon name="check" size={13} /></span> : <span className="perm-no">—</span>}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="evidence-note">Roles map to identity-provider groups at login — e.g. an Auditor sees only the audit log and read-only dashboards.</p>
              </Card>
            </div>
          )}

          {sec === "ignore" && (
            <Card title="Ignore rules" subtitle="allowlist · documented, time-boxed exceptions"
              action={<button className="btn btn-mini"><Icon name="plus" size={13} />Add rule</button>}>
              <div className="ignore-best"><Icon name="check" size={13} />Every rule needs a reason and an expiry. Expired rules resurface automatically on the next sweep.</div>
              <table className="tbl tbl-bordered">
                <thead><tr><th>Vulnerability</th><th>Scope</th><th>Reason</th><th>Added by</th><th>Expires</th><th></th></tr></thead>
                <tbody>
                  {s.ignoreRules.map((r) => (
                    <tr key={r.id}>
                      <td className="mono-cell strong">{r.id}</td>
                      <td className="mono-cell sm">{r.scope}</td>
                      <td className="wrap-cell">{r.reason}</td>
                      <td className="sm">{r.by}</td>
                      <td className="mono-cell sm">{r.expires}</td>
                      <td className="c"><button className="icon-del" onClick={() => set("ignoreRules", s.ignoreRules.filter((x) => x.id !== r.id))}><Icon name="trash" size={14} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Row label="Always surface KEV / high-EPSS" hint="Override ignore rules when a CVE is known-exploited or scores high on EPSS." stack>
                <Toggle on={true} onChange={() => {}} />
              </Row>
            </Card>
          )}

          {sec === "db" && (
            <div className="stack">
              <div className="ignore-best" style={{ marginBottom: 0 }}><Icon name="layers" size={13} />Each scanner has its own database with a different distribution model. javv refreshes both on a schedule (not per-scan) into a persistent cache to avoid registry rate limits.</div>
              <div className="db-tabs">
                <Seg value={dbScanner} onChange={setDbScanner} options={[{ v: "trivy", label: "Trivy DB" }, { v: "grype", label: "Grype DB" }]} />
                <span className="db-cache mono-cell sm">cache · {s.vulnDb.cacheVolume}</span>
              </div>

              {dbScanner === "trivy" && (
                <Card title={<span className="set-card-title"><ScannerTag name="Trivy" /> Trivy database</span>} subtitle="OCI artifact pulled from a registry · ghcr.io/aquasecurity by default">
                  <Row label="Vuln DB repository" stack hint="--db-repository · OCI reference. Point at a mirror for air-gapped clusters.">
                    <input className="text-input mono-cell" value={s.vulnDb.trivy.dbRepository} onChange={(e) => set("vulnDb.trivy.dbRepository", e.target.value)} />
                  </Row>
                  <Row label="Java DB repository" stack hint="--java-db-repository · separate OCI artifact for JAR matching.">
                    <input className="text-input mono-cell" value={s.vulnDb.trivy.javaDbRepository} onChange={(e) => set("vulnDb.trivy.javaDbRepository", e.target.value)} />
                  </Row>
                  <Row label="Refresh cadence" hint="How often the DB artifact is re-pulled into cache.">
                    <Seg value={s.vulnDb.trivy.refresh} onChange={(v) => set("vulnDb.trivy.refresh", v)} options={[{ v: "6h", label: "6h" }, { v: "12h", label: "12h" }, { v: "24h", label: "24h" }]} />
                  </Row>
                  <Row label="Skip DB update" hint="--skip-db-update · use only the cached DB, never fetch. For locked-down runs.">
                    <Toggle on={s.vulnDb.trivy.skipUpdate} onChange={(v) => set("vulnDb.trivy.skipUpdate", v)} />
                  </Row>
                  <Row label="Current DB built" hint="Age of the cached database."><RelTime rel={s.vulnDb.trivy.builtRel} abs={s.vulnDb.trivy.builtAbs} /></Row>
                </Card>
              )}

              {dbScanner === "grype" && (
                <Card title={<span className="set-card-title"><ScannerTag name="Grype" /> Grype database</span>} subtitle="listing.json over HTTP · GRYPE_DB_* environment">
                  <Row label="DB update URL" stack hint="GRYPE_DB_UPDATE_URL · points at the listing.json on your file server or mirror.">
                    <input className="text-input mono-cell" value={s.vulnDb.grype.updateUrl} onChange={(e) => set("vulnDb.grype.updateUrl", e.target.value)} />
                  </Row>
                  <Row label="Custom CA certificate" stack hint="GRYPE_DB_CA_CERT · path to the CA for a self-signed mirror endpoint.">
                    <input className="text-input mono-cell" value={s.vulnDb.grype.caCert} onChange={(e) => set("vulnDb.grype.caCert", e.target.value)} />
                  </Row>
                  <Row label="Auto-update" hint="GRYPE_DB_AUTO_UPDATE · fetch a newer DB from the URL above when available.">
                    <Toggle on={s.vulnDb.grype.autoUpdate} onChange={(v) => set("vulnDb.grype.autoUpdate", v)} />
                  </Row>
                  <Row label="Max allowed built age" hint="GRYPE_DB_MAX_ALLOWED_BUILT_AGE · scan fails if the DB is older than this.">
                    <Seg value={s.vulnDb.grype.maxBuiltAge} onChange={(v) => set("vulnDb.grype.maxBuiltAge", v)} options={[{ v: "48h", label: "48h" }, { v: "120h", label: "120h" }, { v: "240h", label: "240h" }]} />
                  </Row>
                  <Row label="Validate DB age" hint="GRYPE_DB_VALIDATE_AGE · enforce the staleness check above.">
                    <Toggle on={s.vulnDb.grype.validateAge} onChange={(v) => set("vulnDb.grype.validateAge", v)} />
                  </Row>
                  <Row label="Current DB built" hint="Age of the cached database."><RelTime rel={s.vulnDb.grype.builtRel} abs={s.vulnDb.grype.builtAbs} /></Row>
                </Card>
              )}
            </div>
          )}

          {sec === "access" && (
            <Card title="Access & registries" subtitle="ingest auth and private registry credentials">
              <div className="scanner-banner"><Icon name="shield" size={14} />Every scanner type pushes over <b>HTTPS only</b>, authenticated by a scoped API access token — no other credentials touch the ingest endpoint.</div>
              <Row label="Transport" hint="TLS termination at the ingest endpoint. Plain HTTP is rejected." stack>
                <div className="token-row"><div className="fld fld-static mono-cell" style={{ flex: 1 }}>https:// · TLS 1.2+ enforced</div><span className="lock-tag">immutable</span></div>
              </Row>
              <Row label="Push tokens" stack hint="One scoped token per scanner. Any scanner type that holds a valid token can push — nothing else is required.">
                <table className="tbl tbl-bordered">
                  <thead><tr><th>Scanner</th><th>Token</th><th>Scope</th><th>Created</th><th>Last used</th><th></th></tr></thead>
                  <tbody>
                    {s.access.pushTokens.map((t) => (
                      <tr key={t.scanner}>
                        <td><ScannerTag name={t.scanner} /></td>
                        <td className="mono-cell sm">{t.token}</td>
                        <td className="mono-cell sm muted">{t.scope}</td>
                        <td className="mono-cell sm muted">{t.created}</td>
                        <td><RelTime rel={t.lastUsed} abs={t.lastUsedAbs} /></td>
                        <td className="c"><div className="token-actions"><button className="btn btn-mini">Rotate</button><button className="btn btn-mini">Revoke</button></div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button className="btn btn-mini" style={{ marginTop: 10 }}><Icon name="plus" size={13} />Add scanner token</button>
              </Row>
              <Row label="Auto-resolve imagePullSecrets" hint="Resolve dockerconfigjson → pass creds to the scanner. Held in memory only, never logged.">
                <Toggle on={s.access.autoResolveSecrets} onChange={(v) => set("access.autoResolveSecrets", v)} />
              </Row>
              <Row label="Known registries" stack hint="Private registries the scanner has resolved credentials for.">
                <Chips placeholder="registry.example.com" items={s.access.registries}
                  onAdd={(v) => set("access.registries", [...s.access.registries, v])}
                  onRemove={(v) => set("access.registries", s.access.registries.filter((x) => x !== v))} />
              </Row>
            </Card>
          )}

          {sec === "cluster" && (
            <Card title="Cluster" subtitle="identity & ingest contract">
              <Row label="cluster_id" stack hint="Derived from the kube-system namespace UID — immutable.">
                <div className="token-row"><div className="fld fld-static mono-cell" style={{ flex: 1 }}>{JAVV.clusters[0].id}</div><span className="lock-tag">immutable</span></div>
              </Row>
              <Row label="cluster_name" stack hint="Relabelable display name. Multi-cluster is keyed on cluster_id.">
                <input className="text-input" defaultValue={JAVV.clusters[0].name} onChange={touch} />
              </Row>
              <Row label="Ingest endpoint" stack><div className="fld fld-static mono-cell">https://ingest.example.com/v1</div></Row>
              <div className="set-row-2col">
                <Row label="API version"><div className="fld fld-static mono-cell">/v1</div></Row>
                <Row label="schema_version"><div className="fld fld-static mono-cell">3</div></Row>
              </div>
            </Card>
          )}
          </div>

          <SaveBar dirty={dirty} onSave={() => setDirty(false)} onDiscard={() => { setS(JSON.parse(JSON.stringify(cfg))); setDirty(false); }} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Settings });
