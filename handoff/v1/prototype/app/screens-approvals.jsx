/* JAVV - Approval list / audit trail */
function Approvals({ go }) {
  const all = JAVV.approvals;
  const approvers = [...new Set(all.map((r) => r.approver))];
  const FIELDS = [
    { key: "sev", label: "Severity", values: [...new Set(all.map((r) => r.sev))], render: (k) => <Sev level={k} />, valLabel: (k) => k },
    { key: "status", label: "Status", values: [...new Set(all.map((r) => r.status))], render: (k) => <StateTag state={k} />, valLabel: (k) => k },
    { key: "approver", label: "Approver", values: approvers, render: (k) => <span className={k === "-" ? "muted" : ""}>{k === "-" ? "Pending" : k}</span>, valLabel: (k) => k === "-" ? "Pending" : k },
  ];
  const { sel, toggle, clearField, clearAll } = useFilters(FIELDS);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [per, setPer] = useState(10);

  const matchVal = (field, val, r) => r[field] === val;
  const countVal = (field, val) => all.filter((r) => matchVal(field, val, r)).length;
  const list = all.filter((r) =>
    (!sel.sev.size || sel.sev.has(r.sev)) &&
    (!sel.status.size || sel.status.has(r.status)) &&
    (!sel.approver.size || sel.approver.has(r.approver)) &&
    (!q || (r.id + r.justification + r.approver + r.task).toLowerCase().includes(q.toLowerCase()))
  );
  useEffect(() => { setPage(0); }, [sel, q, per]);
  const rows = list.slice(page * per, page * per + per);

  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Approval list</h1>
          <p className="screen-sub"><b>{fmt(list.length)}</b> of {all.length} decisions · justification, impact, action &amp; approver per finding</p>
        </div>
        <div className="screen-head-actions">
          <button className="btn btn-ghost"><Icon name="download" size={14} />Export CSV</button>
        </div>
      </div>

      <div className="findings-layout">
        <FacetRail fields={FIELDS} sel={sel} toggle={toggle} countVal={countVal}
          header={
            <div className="facet-search">
              <Icon name="search" size={14} />
              <input placeholder="CVE, justification, task…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          } />

        <div className="findings-main">
          <FilterBar fields={FIELDS} sel={sel} toggle={toggle} clearField={clearField} clearAll={clearAll} countVal={countVal} />

      <Card pad={false}>
        <table className="tbl tbl-approvals tbl-hover">
          <thead>
            <tr><th>Vulnerability</th><th>Severity</th><th>Status</th><th>Justification</th><th>Impact statement</th><th>Action statement</th><th>Approver</th><th>Task</th><th>Date</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} onClick={() => go("finding", { cve: r.id, severity: r.sev })}>
                <td className="mono-cell strong">{r.id}</td>
                <td><Sev level={r.sev} /></td>
                <td><StateTag state={r.status} /></td>
                <td className="wrap-cell">{r.justification}</td>
                <td className="wrap-cell muted">{r.impact}</td>
                <td className="wrap-cell muted">{r.action}</td>
                <td>{r.approver}</td>
                <td className="mono-cell sm"><span className="task-link">{r.task}</span></td>
                <td><RelTime rel={r.whenRel} abs={r.when} /></td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr><td colSpan={9} className="empty-row">No decisions match these filters. <button className="link-btn" onClick={clearAll}>Clear all</button></td></tr>
            )}
          </tbody>
        </table>
      </Card>
      <Pager total={list.length} page={page} setPage={setPage} per={per} setPer={setPer} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Approvals });
