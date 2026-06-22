/* JAVV - Findings grid. Filtering UI comes from app/filters.jsx (useFilters/FacetRail/FilterBar/ColumnsMenu). */
function Findings({ go, preset, cluster }) {
  const all = JAVV.findings;

  const namespacesFlat = JAVV.namespaces.map((n) => n.ns);
  const types = [...new Set(all.map((f) => f.ptype))];
  const assigneeMap = {}; all.forEach((f) => { if (f.assignee) assigneeMap[f.assignee.name] = f.assignee; });
  const assigneeNames = Object.keys(assigneeMap);
  const FIELDS = [
    { key: "severity", label: "Severity", values: ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"], render: (k) => <Sev level={k} />, valLabel: (k) => k },
    { key: "scanner", label: "Scanner", values: ["Trivy", "Grype"], render: (k) => <ScannerTag name={k} />, valLabel: (k) => k },
    { key: "attr", label: "Attribute", values: ["kev", "hasfix", "disagree"], render: (k) => k === "kev" ? <span className="kev-tag">KEV</span> : k === "hasfix" ? <span>Fix available</span> : <span className="disagree-tag"><Icon name="alert" size={11} />Scanners disagree</span>, valLabel: (k) => k === "kev" ? "KEV" : k === "hasfix" ? "Fix available" : "Scanners disagree" },
    { key: "state", label: "State", values: ["open", "stale", "acknowledged", "resolved"], render: (k) => <StateTag state={k} />, valLabel: (k) => k },
    { key: "assignee", label: "Assignee", values: [...assigneeNames, "Unassigned"], render: (k) => k === "Unassigned" ? <span className="muted">Unassigned</span> : <span className="assignee-mini"><Avatar initials={assigneeMap[k].initials} tone={assigneeMap[k].tone} size={20} />{k}</span>, valLabel: (k) => k },
    { key: "ns", label: "Namespace", values: namespacesFlat, render: (k) => <span className="mono-cell sm">{k}</span>, valLabel: (k) => k },
    { key: "ptype", label: "Package type", values: types, render: (k) => <span className="pkg-type" style={{ fontStyle: "normal" }}>{k}</span>, valLabel: (k) => k },
  ];

  const { sel, toggle, clearField, clearAll, hasFilters } = useFilters(FIELDS, preset);
  const [q, setQ] = useState(preset && preset.q ? preset.q : "");
  const [sort, setSort] = useState({ k: "severity", dir: 1 });
  const [page, setPage] = useState(0);
  const [per, setPer] = useState(25);
  const [checked, setChecked] = useState(new Set());
  const [hidden, setHidden] = useState(new Set());
  const [dense, setDense] = useState(true);
  const [savedMsg, setSavedMsg] = useState(false);
  const [exp, setExp] = useState(false);

  const count = (fn) => all.filter(fn).length;
  const show = (k) => !hidden.has(k);
  const toggleCol = (k) => setHidden((prev) => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const matchVal = (field, val, f) => {
    if (field === "attr") return val === "kev" ? f.kev : val === "hasfix" ? !!f.fixed : !!f.disagree;
    if (field === "assignee") return val === "Unassigned" ? !f.assignee : !!(f.assignee && f.assignee.name === val);
    return f[field] === val;
  };
  const countVal = (field, val) => count((f) => matchVal(field, val, f));

  const SEV_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
  const STATE_RANK = { open: 0, stale: 1, acknowledged: 2, resolved: 3 };
  const filtered = useMemo(() => {
    let r = all.filter((f) =>
      (!sel.severity.size || sel.severity.has(f.severity)) &&
      (!sel.scanner.size || sel.scanner.has(f.scanner)) &&
      (!sel.ns.size || sel.ns.has(f.ns)) &&
      (!sel.ptype.size || sel.ptype.has(f.ptype)) &&
      (!sel.state.size || sel.state.has(f.state)) &&
      (!sel.attr.size || [...sel.attr].every((v) => matchVal("attr", v, f))) &&
      (!sel.assignee.size || [...sel.assignee].some((v) => matchVal("assignee", v, f))) &&
      (!q || f.cve.toLowerCase().includes(q.toLowerCase()) || f.pkg.includes(q.toLowerCase()) || f.component.includes(q.toLowerCase()))
    );
    r = [...r].sort((a, b) => {
      let av, bv;
      if (sort.k === "severity") { av = SEV_RANK[a.severity]; bv = SEV_RANK[b.severity]; }
      else if (sort.k === "epss") { av = a.scanner === "Grype" ? a.epss : -1; bv = b.scanner === "Grype" ? b.epss : -1; }
      else if (sort.k === "state") { av = STATE_RANK[a.state]; bv = STATE_RANK[b.state]; }
      else if (sort.k === "assignee") { av = a.assignee ? a.assignee.name : "zzz"; bv = b.assignee ? b.assignee.name : "zzz"; }
      else { av = a[sort.k]; bv = b[sort.k]; }
      return (av > bv ? 1 : av < bv ? -1 : 0) * sort.dir;
    });
    return r;
  }, [sel, q, sort]);

  useEffect(() => { setPage(0); setChecked(new Set()); }, [sel, q, per]);
  const rows = filtered.slice(page * per, page * per + per);
  const pageIds = rows.map((f) => f.id);
  const allChecked = pageIds.length > 0 && pageIds.every((id) => checked.has(id));
  const toggleRow = (id) => setChecked((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const togglePage = () => setChecked((prev) => {
    const n = new Set(prev);
    allChecked ? pageIds.forEach((id) => n.delete(id)) : pageIds.forEach((id) => n.add(id));
    return n;
  });

  const sortBy = (k) => setSort((s) => ({ k, dir: s.k === k ? -s.dir : 1 }));
  const arrow = (k) => sort.k === k ? <span className="sort-arrow">{sort.dir > 0 ? "↑" : "↓"}</span> : null;

  const COLS = [["epss", "EPSS"], ["kev", "KEV"], ["component", "Component"], ["pkg", "Package"], ["current", "Current"], ["fixed", "Fixed"], ["scanner", "Scanner"], ["sla", "SLA"], ["state", "State"], ["assignee", "Assignee"]];
  const saveView = () => { setSavedMsg(true); setTimeout(() => setSavedMsg(false), 2200); };

  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Findings</h1>
          <p className="screen-sub"><b>{fmt(filtered.length)}</b> of {fmt(all.length)} findings · kept per-scanner, no cross-merge</p>
        </div>
        <div className="screen-head-actions">
          <button className="btn btn-ghost" onClick={() => go("views")}><Icon name="bookmark" size={14} />Saved views</button>
          <Gate cap="can_export" disable><button className="btn btn-ghost" disabled={!can("can_export")} onClick={() => setExp(true)}><Icon name="download" size={14} />Export CSV</button></Gate>
        </div>
      </div>

      <div className="findings-layout">
        <FacetRail fields={FIELDS} sel={sel} toggle={toggle} countVal={countVal}
          header={
            <div className="facet-search">
              <Icon name="search" size={14} />
              <input placeholder="CVE, package, component…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          } />

        <div className="findings-main">
          <div className="toolbar-row">
            <FilterBar fields={FIELDS} sel={sel} toggle={toggle} clearField={clearField} clearAll={clearAll} countVal={countVal}
              extra={hasFilters && <button className="save-view" onClick={saveView}><Icon name="bookmark" size={12} />{savedMsg ? "Saved ✓" : "Save view"}</button>} />
            <ColumnsMenu cols={COLS} hidden={hidden} toggleCol={toggleCol} dense={dense} setDense={setDense} />
          </div>
          <div className="server-note"><Icon name="layers" size={13} />All sort / filter / facet counts computed server-side via OpenSearch aggregations</div>

          {checked.size > 0 && (
            <div className="bulk-bar">
              <span className="bulk-count">{checked.size} selected</span>
              <button className="btn btn-mini" onClick={() => setChecked(new Set())}><Icon name="check" size={13} />Acknowledge</button>
              <button className="btn btn-mini">Assign…</button>
              <button className="btn btn-mini"><Icon name="download" size={13} />Export selected</button>
              <button className="bulk-clear" onClick={() => setChecked(new Set())}>Clear selection</button>
            </div>
          )}

          <div className="tbl-wrap">
            <table className={"tbl tbl-hover " + (dense ? "tbl-dense" : "")}>
              <thead>
                <tr>
                  <th className="chk-col"><button className={"row-chk " + (allChecked ? "row-chk-on" : "")} onClick={togglePage} aria-label="select page" /></th>
                  <th onClick={() => sortBy("cve")} className="sortable">Vulnerability {arrow("cve")}</th>
                  <th onClick={() => sortBy("severity")} className="sortable">Severity {arrow("severity")}</th>
                  {show("epss") && <th onClick={() => sortBy("epss")} className="sortable r">EPSS<span className="th-note">via Grype</span> {arrow("epss")}</th>}
                  {show("kev") && <th className="c">KEV</th>}
                  {show("component") && <th>Component</th>}
                  {show("pkg") && <th>Package</th>}
                  {show("current") && <th>Current</th>}
                  {show("fixed") && <th>Fixed</th>}
                  {show("scanner") && <th>Scanner</th>}
                  {show("sla") && <th onClick={() => sortBy("sla")} className="sortable c">SLA {arrow("sla")}</th>}
                  {show("state") && <th onClick={() => sortBy("state")} className="sortable">State {arrow("state")}</th>}
                  {show("assignee") && <th onClick={() => sortBy("assignee")} className="sortable">Assignee {arrow("assignee")}</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((f) => (
                  <tr key={f.id} onClick={() => go("finding", f)} className={checked.has(f.id) ? "row-checked" : ""}>
                    <td className="chk-col" onClick={(e) => { e.stopPropagation(); toggleRow(f.id); }}>
                      <button className={"row-chk " + (checked.has(f.id) ? "row-chk-on" : "")} aria-label="select row" />
                    </td>
                    <td className="mono-cell strong">{f.cve}</td>
                    <td><Sev level={f.severity} /></td>
                    {show("epss") && <td className="r">{f.scanner === "Grype" ? <Epss v={f.epss} /> : <span className="muted-dash" title="EPSS enrichment arrives with Grype results only">-</span>}</td>}
                    {show("kev") && <td className="c"><Kev on={f.kev} /></td>}
                    {show("component") && <td className="mono-cell">{f.component}</td>}
                    {show("pkg") && <td><span className="pkg">{f.pkg}<i className="pkg-type">{f.ptype}</i></span></td>}
                    {show("current") && <td className="mono-cell sm"><span className="ver-cur">{f.current}</span></td>}
                    {show("fixed") && <td className="mono-cell sm">{f.fixed ? <span className="ver-fix">{f.fixed}</span> : <span className="ver-none">no fix</span>}</td>}
                    {show("scanner") && <td>
                      <span className="scanner-stack">
                        <ScannerTag name={f.scanner} />
                        {f.disagree && <span className="disagree-tag" title={`${f.scanner}: ${f.severity} · ${f.scanner === "Trivy" ? "Grype" : "Trivy"}: ${f.disagree}`}><Icon name="alert" size={11} />±</span>}
                      </span>
                    </td>}
                    {show("sla") && <td className="c"><Sla days={f.sla} overdue={f.overdue} /></td>}
                    {show("state") && <td><StateTag state={f.state} /></td>}
                    {show("assignee") && <td>{f.assignee ? <span className="assignee-cell"><Avatar initials={f.assignee.initials} tone={f.assignee.tone} size={22} />{f.assignee.name.split(" ")[0]}</span> : <span className="assignee-none"><i className="av-empty" />Unassigned</span>}</td>}
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={13} className="empty-row">No findings match these filters. <button className="link-btn" onClick={clearAll}>Clear all</button></td></tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager total={filtered.length} page={page} setPage={setPage} per={per} setPer={setPer} />
        </div>
      </div>
      {exp && <ExportDialog scope={`Findings · ${filtered.length} of ${all.length}`} rows={filtered.length} onClose={() => setExp(false)} />}
    </div>
  );
}

Object.assign(window, { Findings });
