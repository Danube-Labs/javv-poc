/* JAVV - Saved views: named filter sets, Kibana-dashboards style */
function SavedViews({ go }) {
  const FIELD_LABEL = { severity: "Severity", scanner: "Scanner", ns: "Namespace", ptype: "Package type", state: "State", attr: "Attribute", assignee: "Assignee" };
  const ATTR_LABEL = { kev: "KEV", hasfix: "Fix available", disagree: "Scanners disagree" };
  const countFor = (filters) => {
    return JAVV.findings.filter((f) =>
      Object.entries(filters).every(([k, vals]) => {
        if (k === "attr") return vals.every((v) => v === "kev" ? f.kev : v === "hasfix" ? !!f.fixed : !!f.disagree);
        if (k === "assignee") return vals.some((v) => v === "Unassigned" ? !f.assignee : f.assignee && f.assignee.name === v);
        return vals.includes(f[k]);
      })
    ).length;
  };
  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Saved views</h1>
          <p className="screen-sub">Named filter sets over Findings · shareable, one click to open</p>
        </div>
        <div className="screen-head-actions">
          <button className="btn btn-primary" onClick={() => go("findings")}><Icon name="plus" size={14} />New view</button>
        </div>
      </div>

      <div className="views-grid">
        {JAVV.savedViews.map((v) => (
          <button className="view-card" key={v.name} onClick={() => go("findings", { filters: v.filters })}>
            <div className="view-card-top">
              <Icon name="bookmark" size={15} />
              <span className="view-name">{v.name}</span>
              <span className="view-count">{fmt(countFor(v.filters))}</span>
            </div>
            <p className="view-desc">{v.desc}</p>
            <div className="view-pills">
              {Object.entries(v.filters).map(([k, vals]) => (
                <span className="view-pill" key={k}>
                  <em>{FIELD_LABEL[k]}</em> {vals.map((x) => k === "attr" ? ATTR_LABEL[x] : x).join(", ")}
                </span>
              ))}
            </div>
            <div className="view-foot">
              <span className="view-owner">by {v.owner}</span>
              <span className="view-open">Open <Icon name="chevron" size={12} /></span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { SavedViews });
