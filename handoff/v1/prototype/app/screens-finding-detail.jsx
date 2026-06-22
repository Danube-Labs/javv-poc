/* JAVV - Finding detail + triage / audit workflow */
function FindingDetail({ go, finding }) {
  const f = JAVV.focusFinding;
  // merge in the row the user clicked (for cve/severity continuity) but keep the rich record
  const cve = finding && finding.cve ? finding.cve : f.cve;
  const sev = finding && finding.severity ? finding.severity : f.severity;
  const [state, setState] = useState(f.state);
  const [just, setJust] = useState("");
  const [impact, setImpact] = useState("");
  const [action, setAction] = useState("");
  const c = SEV_COLOR[sev];

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

        {/* TRIAGE / AUDIT PANEL - the differentiator */}
        <aside className="triage">
          <div className="triage-head">
            <Icon name="shield" size={16} /><span>Triage</span>
            <StateTag state={state} />
          </div>
          <div className="triage-body">
            <label className="fld-label">Assigned to</label>
            <div className="assignee-field">
              <span className="assignee-cell"><Avatar initials={f.assignee.initials} tone={f.assignee.tone} size={24} />{f.assignee.name}</span>
              <div className="assignee-actions">
                <button className="btn btn-mini">Assign to me</button>
                <button className="btn btn-mini">Reassign</button>
              </div>
            </div>
            <label className="fld-label">State</label>
            <div className="state-picker">
              {[["open", "Open"], ["acknowledged", "Acknowledge"], ["resolved", "Resolve"]].map(([k, lbl]) => (
                <button key={k} className={"state-opt " + (state === k ? "state-opt-on " + STATE_STYLE[k].cls : "")} onClick={() => setState(k)}>{lbl}</button>
              ))}
            </div>
            <p className="triage-hint"><Icon name="clock" size={12} />Staleness is automatic - findings not re-pushed within the cadence window flip to <b>stale</b> on the daily sweep. <b>resolved</b> is manual only.</p>

            <label className="fld-label">Justification</label>
            <textarea className="fld" rows={3} placeholder="Why is this being acknowledged / resolved?" value={just} onChange={(e) => setJust(e.target.value)} />

            <label className="fld-label">Impact statement</label>
            <textarea className="fld" rows={2} placeholder="Reachability, exposure, mitigating controls…" value={impact} onChange={(e) => setImpact(e.target.value)} />

            <label className="fld-label">Action statement</label>
            <textarea className="fld" rows={2} placeholder="What will be done, and when" value={action} onChange={(e) => setAction(e.target.value)} />

            <div className="fld-2">
              <div><label className="fld-label">Approver</label><div className="fld fld-static">Lorem Ipsum</div></div>
              <div><label className="fld-label">Task</label><input className="fld" placeholder="TASK-…" defaultValue="TASK-1250" /></div>
            </div>

            <button className="btn btn-primary btn-block">Save to audit trail</button>
            <button className="btn btn-ghost btn-block" onClick={() => go("approvals")}>View approval list</button>
          </div>
        </aside>
      </div>
    </div>
  );
}

Object.assign(window, { FindingDetail });
