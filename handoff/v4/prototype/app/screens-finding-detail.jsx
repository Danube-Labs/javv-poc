/* JAVV - Finding detail + triage / audit workflow (v4 VEX model) */
function RiskAcceptDialog({ cve, onClose }) {
  const nsList = JAVV.namespaces.map((n) => n.ns);
  const imgList = JAVV.images.map((i) => i.name + ":" + i.tag);
  const [nsSel, setNsSel] = useState(new Set());
  const [imgSel, setImgSel] = useState(new Set());
  const [both, setBoth] = useState(true);
  const tog = (set, setter) => (v) => setter((p) => { const n = new Set(p); n.has(v) ? n.delete(v) : n.add(v); return n; });
  const cluster = nsSel.size === 0 && imgSel.size === 0;
  const imgCount = cluster ? JAVV.images.length : (imgSel.size + nsSel.size * 4);
  return (
    <Modal title="Risk-accept this CVE" subtitle={cve} onClose={onClose} width={560}>
      <div className="ra-anchor"><span className="mono-cell strong">{cve}</span><span className="ra-anchor-note">A decision is anchored on the CVE + scope, so a package bump auto-inherits it.</span></div>
      <label className="fld-label">Scope - namespaces</label>
      <div className="ra-chips">
        {nsList.slice(0, 6).map((ns) => (
          <button key={ns} className={"ra-chip " + (nsSel.has(ns) ? "ra-chip-on" : "")} onClick={() => tog(nsSel, setNsSel)(ns)}>{ns}</button>
        ))}
      </div>
      <label className="fld-label">Scope - images</label>
      <div className="ra-chips">
        {imgList.slice(0, 6).map((im) => (
          <button key={im} className={"ra-chip mono-cell " + (imgSel.has(im) ? "ra-chip-on" : "")} onClick={() => tog(imgSel, setImgSel)(im)}>{im}</button>
        ))}
      </div>
      <div className="ra-blast">
        <Icon name="layers" size={14} />
        <span>Blast radius: <b>{cluster ? "cluster-wide - all " + JAVV.images.length + " images" : "~" + imgCount + " images"}</b>
        {cluster || nsSel.size > 0 ? <em> · namespace/cluster scope auto-applies to NEW matching findings</em> : <em> · image scope does not cascade to new images</em>}</span>
      </div>
      <div className="fld-2">
        <div><label className="fld-label">Expiry</label><input className="fld" type="date" defaultValue="2026-09-15" /></div>
        <div><label className="fld-label">Apply to both scanners</label><div className="seg" style={{ marginTop: 2 }}><button className={"seg-opt " + (both ? "seg-on" : "")} onClick={() => setBoth(true)}>Both</button><button className={"seg-opt " + (!both ? "seg-on" : "")} onClick={() => setBoth(false)}>This scanner</button></div></div>
      </div>
      <label className="fld-label">Justification</label>
      <textarea className="fld" rows={3} placeholder="Why is this risk acceptable, and for how long?" />
      <p className="ra-note"><Icon name="info" size={12} />Decisions are immutable. Editing later <b>revokes and re-creates</b> - the old one stays in history, struck through.</p>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={onClose}>Create decision</button>
      </div>
    </Modal>
  );
}

function FindingDetail({ go, finding }) {
  const f = JAVV.focusFinding;
  // merge in the row the user clicked (for cve/severity continuity) but keep the rich record
  const cve = finding && finding.cve ? finding.cve : f.cve;
  const sev = finding && finding.severity ? finding.severity : f.severity;
  const [state, setState] = useState(f.state);
  const [vexJust, setVexJust] = useState(null);
  const [note, setNote] = useState("");
  const [raOpen, setRaOpen] = useState(false);
  const c = SEV_COLOR[sev];
  const triageLocked = !can("can_triage");
  // decisions touching this CVE
  const cveDecisions = JAVV.decisions.filter((d) => d.cve === cve);
  const readOnlyState = state === "stale" || state === "risk_accepted";

  return (
    <div className="screen">
      <button className="back-link" onClick={() => go("findings")}><Icon name="arrowback" size={15} />Findings</button>

      <div className="detail-head" style={{ "--accent": c.solid }}>
        <div className="detail-head-main">
          <div className="detail-cve">
            <h1>{cve}</h1>
            <Sev level={sev} solid />
            {f.kev && <span className="kev-tag kev-lg">KEV · known-exploited</span>}
          </div>
          <p className="detail-title">{f.title}</p>
          <div className="detail-meta">
            <span><em>CVSS</em> {f.cvss}</span>
            <span><em>EPSS</em> {Math.round(f.epss * 100)}% <i className="muted">(p{f.epssPct} · via Grype)</i></span>
            <span><em>CWE</em> {f.cwe}</span>
            <span><em>Published</em> {f.published}</span>
            <span><em>Discovered</em> {f.discovered}</span>
          </div>
        </div>
        <div className={"sla-box " + (f.overdue ? "sla-box-over" : "")}>
          <span className="sla-box-label">SLA</span>
          <span className="sla-box-days">{f.sla}<em>d</em></span>
          <span className="sla-box-deadline">{f.overdue ? "Overdue" : "by"} {f.slaDeadline}</span>
        </div>
      </div>

      <div className="grid grid-2-1" style={{ marginTop: 16, alignItems: "start" }}>
        <div className="stack">
          <Card title="Description">
            <p className="prose">{f.description}</p>
            <div className="cvss-vector"><span className="mono-cell sm">{f.cvssVector}</span></div>
            <div className="ref-list">
              {f.refs.map((r) => (
                <a key={r} href="#" onClick={(e) => e.preventDefault()} className="ref"><Icon name="external" size={12} />{r.replace("https://", "")}</a>
              ))}
            </div>
          </Card>

          <Card title="Per-scanner evidence" subtitle="raw results - no black box" action={<span className="card-tag">no cross-scanner merge</span>}>
            <table className="tbl tbl-bordered">
              <thead><tr><th>Scanner</th><th>Severity</th><th>Source</th><th>Fixed in</th><th>Match status</th><th>Vuln DB</th></tr></thead>
              <tbody>
                {f.scannerEvidence.map((e) => (
                  <tr key={e.scanner}>
                    <td><ScannerTag name={e.scanner} /></td>
                    <td><Sev level={e.severity} /></td>
                    <td className="mono-cell sm">{e.source}</td>
                    <td className="mono-cell sm ver-fix">{e.fixed}</td>
                    <td><span className="match-fixed"><Icon name="check" size={12} />{e.status}</span></td>
                    <td className="mono-cell sm muted">{e.db}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="evidence-note">Both scanners agree on severity and fixed version. Dashboards facet by scanner so this finding is never double-counted.</p>
          </Card>

          <Card title="Affected components" subtitle="across what's actually running">
            <table className="tbl tbl-hover">
              <thead><tr><th>Component</th><th>Namespace</th><th>Current</th><th>Fixed</th><th className="r">Running images</th></tr></thead>
              <tbody>
                {f.affected.map((a) => (
                  <tr key={a.comp} onClick={() => go("image")}>
                    <td className="mono-cell strong">{a.comp}</td>
                    <td className="mono-cell sm">{a.ns}</td>
                    <td className="mono-cell sm ver-cur">{a.current}</td>
                    <td className="mono-cell sm ver-fix">{a.fixed}</td>
                    <td className="r">{a.images}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>

        {/* TRIAGE / AUDIT PANEL - the differentiator (v4 VEX) */}
        <aside className="triage">
          <div className="triage-head">
            <Icon name="shield" size={16} /><span>Triage</span>
            <StateTag state={state} />
          </div>
          <div className="triage-body">
            {triageLocked && <div className="triage-locked"><Icon name="key" size={13} />Read-only - you don't hold <b>can_triage</b>. Ask an Operator or Security Lead.</div>}

            <label className="fld-label">Assigned to</label>
            <div className="assignee-field">
              <span className="assignee-cell"><Avatar initials={f.assignee.initials} tone={f.assignee.tone} size={24} />{f.assignee.name}</span>
              <Gate cap="can_triage" disable>
                <div className="assignee-actions">
                  <button className="btn btn-mini" disabled={triageLocked}>Assign to me</button>
                  <button className="btn btn-mini" disabled={triageLocked}>Reassign</button>
                </div>
              </Gate>
            </div>

            <label className="fld-label">State · VEX lifecycle</label>
            <div className="state-grid">
              {[["open", "Open"], ["acknowledged", "Acknowledge"], ["not_affected", "Not affected"], ["resolved", "Resolve"]].map(([k, lbl]) => (
                <button key={k} disabled={triageLocked} className={"state-opt " + (state === k ? "state-opt-on " + STATE_STYLE[k].cls : "")} onClick={() => setState(k)}>{lbl}</button>
              ))}
            </div>

            {state === "not_affected" && (
              <div className="vex-block">
                <label className="fld-label">Justification · CISA five (required)</label>
                <div className="vex-chips">
                  {JAVV.vexJustifications.map((j) => (
                    <button key={j.id} disabled={triageLocked} className={"vex-chip " + (vexJust === j.id ? "vex-chip-on" : "")} onClick={() => setVexJust(j.id)} title={j.note}>
                      <span className="vex-chip-label">{j.label}</span>
                      <span className={"vex-maps " + (j.maps === "False positive" ? "vm-fp" : "vm-ne")}>{j.maps}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {state === "risk_accepted" && (
              <div className="ro-state ro-risk">
                <Icon name="shield" size={13} />
                <div><b>Set by a scoped decision</b><span>Risk-accept isn't toggled here - it comes from a decision (scope + approver + expiry). Manage it below.</span></div>
              </div>
            )}
            {state === "stale" && (
              <div className="ro-state ro-stale">
                <Icon name="clock" size={13} />
                <div><b>System-set · scanner went silent</b><span>The scanner stopped reporting this finding - data may be old. <button className="link-btn" disabled={triageLocked}>re-scan to refresh</button></span></div>
              </div>
            )}

            <div className="presence-note">
              <span className="pn-row"><i className="pn-dot pn-fixed" /><b>Fixed</b> - absent from the latest scan → drops off the “now” grid immediately (resolved/gone).</span>
              <span className="pn-row"><i className="pn-dot pn-stale" /><b>Stale</b> - scanner silent → still shown, flagged; presence unknown.</span>
            </div>

            <label className="fld-label">Note <span className="fld-opt">(escaped - never rendered as HTML)</span></label>
            <textarea className="fld" rows={3} placeholder="Add context for the audit trail…" value={note} onChange={(e) => setNote(e.target.value)} disabled={triageLocked} />

            <Gate cap="can_accept_audit_final" disable reason="Risk-accept needs the can_accept_audit_final capability">
              <button className="btn btn-ghost btn-block" disabled={!can("can_accept_audit_final")} onClick={() => setRaOpen(true)}><Icon name="shield" size={14} />Risk-accept this CVE…</button>
            </Gate>
            <button className="btn btn-primary btn-block" disabled={triageLocked}>Save to audit trail</button>
            <p className="triage-foot"><Icon name="clock" size={11} />Every action records who &amp; when. Relative times shown; deadlines absolute.</p>
          </div>
        </aside>
      </div>

      {/* Decisions touching this CVE (active / revoked / expired) */}
      <Card title="Decisions on this CVE" subtitle="scoped risk-accepts &amp; not-affected calls - immutable; edits revoke + re-create" className="mt16"
        action={<Gate cap="can_accept_audit_final"><button className="btn btn-mini" onClick={() => setRaOpen(true)}><Icon name="plus" size={13} />New decision</button></Gate>}>
        <table className="tbl tbl-bordered">
          <thead><tr><th>ID</th><th>Type</th><th>Scope</th><th>Blast radius</th><th>Approver</th><th>Expiry</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {cveDecisions.length === 0 && <tr><td colSpan={8} className="empty-row">No decisions on this CVE yet.</td></tr>}
            {cveDecisions.map((d) => (
              <tr key={d.id} className={d.status !== "active" ? "dec-inactive" : ""}>
                <td className="mono-cell sm strong">{d.id}</td>
                <td>{d.type === "risk_accepted" ? <StateTag state="risk_accepted" /> : <StateTag state="not_affected" />}</td>
                <td className="sm">{d.applyBoth ? <span className="both-tag">both scanners</span> : <ScannerTag name={d.scanner} />}</td>
                <td className="sm">{d.blastRadius}{d.cascades ? <i className="casc-tag">cascades</i> : null}</td>
                <td className="sm">{d.approver}</td>
                <td className="mono-cell sm">{d.expiry}</td>
                <td>{d.status === "active" ? <span className="dec-active">active</span> : <span className={"dec-chip dec-" + d.status}>{d.status}{d.revokedAt ? " · " + d.revokedAt : ""}</span>}</td>
                <td className="c">{d.status === "active" ? <Gate cap="can_accept_audit_final"><button className="btn btn-mini" title="Revoke this acceptance and create a new one" onClick={() => setRaOpen(true)}>Revoke &amp; replace</button></Gate> : null}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {raOpen && <RiskAcceptDialog cve={cve} onClose={() => setRaOpen(false)} />}
    </div>
  );
}

Object.assign(window, { FindingDetail });
