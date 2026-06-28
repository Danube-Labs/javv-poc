/* JAVV - User audit log: who did what, when. Built on the shared filters module. */
function ActionTag({ action }) {
  const M = {
    resolved: ["Resolved", "act-resolved"],
    acknowledged: ["Acknowledged", "act-acknowledged"],
    assigned: ["Assigned", "act-assigned"],
    reassigned: ["Reassigned", "act-assigned"],
    "ignore-rule": ["Ignore rule", "act-ignore"],
    config: ["Config change", "act-config"],
    export: ["Export", "act-config"],
    token: ["Token", "act-config"],
  };
  const [label, cls] = M[action] || [action, "act-config"];
  return <span className={"feed-act " + cls}>{label}</span>;
}

function AuditLog({ go }) {
  const all = JAVV.auditLog;
  const users = [...new Set(all.map((e) => e.user))];
  const userMap = {}; all.forEach((e) => { userMap[e.user] = e; });
  const actions = [...new Set(all.map((e) => e.action))];
  const FIELDS = [
    { key: "action", label: "Action", values: actions, render: (k) => <ActionTag action={k} />, valLabel: (k) => k },
    { key: "user", label: "User", values: users, render: (k) => <span className="assignee-mini"><Avatar initials={userMap[k].initials} tone={userMap[k].tone} size={18} />{k.split(" ")[0]}</span>, valLabel: (k) => k },
  ];
  const { sel, toggle, clearField, clearAll } = useFilters(FIELDS);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [per, setPer] = useState(10);

  const countVal = (field, val) => all.filter((e) => e[field] === val).length;
  const list = all.filter((e) =>
    (!sel.action.size || sel.action.has(e.action)) &&
    (!sel.user.size || sel.user.has(e.user)) &&
    (!q || (e.user + e.target + e.detail).toLowerCase().includes(q.toLowerCase()))
  );
  useEffect(() => { setPage(0); }, [sel, q, per]);
  const rows = list.slice(page * per, page * per + per);

  const resolved30 = all.filter((e) => e.action === "resolved").length;
  const isFinding = (e) => /^(CVE|ADV)-/.test(e.target);

  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Audit log</h1>
          <p className="screen-sub"><b>{fmt(list.length)}</b> of {all.length} events · every state change, assignment, config edit &amp; export - immutable, per user</p>
        </div>
        <div className="screen-head-actions">
          <button className="btn btn-ghost" onClick={() => go("heroes")}><Icon name="award" size={14} />Contributors</button>
          <button className="btn btn-ghost"><Icon name="download" size={14} />Export CSV</button>
        </div>
      </div>

      <div className="findings-layout">
        <FacetRail fields={FIELDS} sel={sel} toggle={toggle} countVal={countVal}
          header={
            <div className="facet-search">
              <Icon name="search" size={14} />
              <input placeholder="user, CVE, detail…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          } />

        <div className="findings-main">
          <FilterBar fields={FIELDS} sel={sel} toggle={toggle} clearField={clearField} clearAll={clearAll} countVal={countVal} />
          <div className="tbl-wrap">
            <table className="tbl tbl-dense tbl-hover">
              <thead>
                <tr><th>When</th><th>User</th><th>Action</th><th>Target</th><th>Detail</th><th>Task</th></tr>
              </thead>
              <tbody>
                {rows.map((e, i) => (
                  <tr key={i} onClick={() => isFinding(e) && go("finding", { cve: e.target, severity: e.sev })} style={isFinding(e) ? {} : { cursor: "default" }}>
                    <td><RelTime rel={e.rel} abs={e.abs} /></td>
                    <td><span className="assignee-cell"><Avatar initials={e.initials} tone={e.tone} size={22} />{e.user}</span></td>
                    <td><ActionTag action={e.action} /></td>
                    <td>
                      <span className="audit-target">
                        <span className="mono-cell strong sm">{e.target}</span>
                        {e.sev && <Sev level={e.sev} dot={false} />}
                      </span>
                    </td>
                    <td className="wrap-cell muted">{e.detail}</td>
                    <td className="mono-cell sm">{e.task ? <span className="task-link">{e.task}</span> : <span className="muted-dash">-</span>}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={6} className="empty-row">No events match these filters. <button className="link-btn" onClick={clearAll}>Clear all</button></td></tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager total={list.length} page={page} setPage={setPage} per={per} setPer={setPer} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AuditLog });
