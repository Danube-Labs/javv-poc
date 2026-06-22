/* JAVV - Running images inventory + image detail (Trivy/Grype scanner dropdown) */
function Images({ go, cluster }) {
  const imgs = JAVV.images;
  const [q, setQ] = useState("");
  const nsList = [...new Set(imgs.map((i) => i.ns))];
  const appList = [...new Set(imgs.map((i) => i.app))];
  const FIELDS = [
    { key: "severity", label: "Severity", values: ["CRITICAL", "HIGH", "MEDIUM", "LOW"], render: (k) => <Sev level={k} />, valLabel: (k) => k },
    { key: "scanner", label: "Scanner", values: ["Trivy", "Grype"], render: (k) => <ScannerTag name={k} />, valLabel: (k) => k },
    { key: "fix", label: "Fix", values: ["Fix available", "No fix yet"], render: (k) => k === "Fix available" ? <span className="ver-fix">Fix available</span> : <span className="ver-none">No fix yet</span>, valLabel: (k) => k },
    { key: "ns", label: "Namespace", values: nsList, render: (k) => <span className="mono-cell sm">{k}</span>, valLabel: (k) => k },
    { key: "app", label: "Application", values: appList, render: (k) => <span className="mono-cell sm">{k}</span>, valLabel: (k) => k },
  ];
  const { sel, toggle, clearField, clearAll } = useFilters(FIELDS);
  const [page, setPage] = useState(0);
  const [per, setPer] = useState(10);

  const sevCount = (im) => ({ CRITICAL: im.crit, HIGH: im.high, MEDIUM: im.med, LOW: im.low });
  const matchVal = (field, val, im) => {
    if (field === "scanner") return im.scanners.includes(val);
    if (field === "severity") return sevCount(im)[val] > 0;
    if (field === "fix") return val === "Fix available" ? im.fixable > 0 : im.fixable === 0;
    return im[field] === val;
  };
  const count = (field, val) => imgs.filter((im) => matchVal(field, val, im)).length;
  const countVal = count;

  const list = imgs.filter((im) =>
    (!sel.severity.size || [...sel.severity].some((v) => matchVal("severity", v, im))) &&
    (!sel.scanner.size || [...sel.scanner].some((v) => matchVal("scanner", v, im))) &&
    (!sel.fix.size || [...sel.fix].some((v) => matchVal("fix", v, im))) &&
    (!sel.ns.size || sel.ns.has(im.ns)) &&
    (!sel.app.size || sel.app.has(im.app)) &&
    (!q || (im.name + im.registry + im.ns).toLowerCase().includes(q.toLowerCase()))
  );
  useEffect(() => { setPage(0); }, [sel, q, per]);
  const rows = list.slice(page * per, page * per + per);
  const totalReplicas = imgs.reduce((a, i) => a + i.replicas, 0);

  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Running images</h1>
          <p className="screen-sub">k8s-runtime inventory · <b>{fmt(list.length)}</b> of {imgs.length} images · <b>{totalReplicas}</b> replicas at last sweep · digest-deduped</p>
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
              <input placeholder="image, registry, namespace…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          } />

        <div className="findings-main">
          <FilterBar fields={FIELDS} sel={sel} toggle={toggle} clearField={clearField} clearAll={clearAll} countVal={countVal} />
          <div className="server-note"><Icon name="layers" size={13} />Inventory and counts aggregated server-side · replicas reflect the last completed sweep, not live state</div>
          <div className="tbl-wrap">
            <table className="tbl tbl-dense tbl-hover">
              <thead>
                <tr>
                  <th>Image</th><th>Tag</th><th>Namespace</th><th className="r">Replicas<span className="th-note">observed at last sweep</span></th>
                  <th className="r">Vulns</th><th style={{ width: 150 }}>Severity mix</th><th>Scanners</th><th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((im) => (
                  <tr key={im.name + im.tag} onClick={() => go("image", im)}>
                    <td>
                      <div className="img-cell">
                        <span className="img-name">{im.name}</span>
                        <span className="img-reg mono-cell sm">{im.registry}</span>
                      </div>
                    </td>
                    <td className="mono-cell sm">{im.tag}</td>
                    <td className="mono-cell sm">{im.ns}</td>
                    <td className="r mono-cell">{im.replicas}</td>
                    <td className="r strong">{fmt(im.total)}</td>
                    <td><MixBar crit={im.crit} high={im.high} med={im.med} low={im.low} /></td>
                    <td><span className="scanner-stack">{im.scanners.map((s) => <ScannerTag key={s} name={s} />)}</span></td>
                    <td><RelTime rel={im.seenRel} abs={im.seenAbs} /></td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={8} className="empty-row">No images match these filters. <button className="link-btn" onClick={clearAll}>Clear all</button></td></tr>
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

function ImageDetail({ go, image }) {
  const im = image && image.name ? image : JAVV.images[0];
  const [scanner, setScanner] = useState(im.scanners[0]);
  const [open, setOpen] = useState(false);

  const rows = useMemo(() => {
    const base = JAVV.findings.filter((f) => f.scanner === scanner).slice(0, 9);
    return base.map((f) => ({ ...f, component: im.name }));
  }, [scanner, im.name]);

  const counts = { CRITICAL: im.crit, HIGH: im.high, MEDIUM: im.med, LOW: im.low };

  return (
    <div className="screen">
      <button className="back-link" onClick={() => go("images")}><Icon name="arrowback" size={15} />Running images</button>

      <div className="img-detail-head">
        <div className="img-detail-id">
          <div className="img-cube"><Icon name="cube" size={22} /></div>
          <div>
            <h1>{im.name}<span className="img-tag-badge">{im.tag}</span></h1>
            <p className="mono-cell sm muted">{im.registry}/{im.name}:{im.tag}</p>
            <div className="img-detail-meta">
              <span className="mono-cell sm"><b>{im.replicas}</b> replicas at last sweep</span>
              <span className="mono-cell sm">{im.ns}</span>
              <span className="mono-cell sm muted">app: {im.app}</span>
              <RelTime rel={"seen " + im.seenRel} abs={im.seenAbs} />
            </div>
          </div>
        </div>

        <div className="scanner-select">
          <label>Showing results from</label>
          <div className="dropdown">
            <button className="dd-btn" onClick={() => setOpen((o) => !o)}>
              <ScannerTag name={scanner} /><span className="dd-img">{im.name}</span><Icon name="chevron" size={14} />
            </button>
            {open && (
              <div className="dd-menu">
                {im.scanners.map((s) => (
                  <button key={s} className={"dd-item " + (s === scanner ? "dd-item-on" : "")} onClick={() => { setScanner(s); setOpen(false); }}>
                    <ScannerTag name={s} /><span className="dd-img">{im.name} - {s}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="sev-summary">
        {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
          <div className="sev-sum" key={s} style={{ "--accent": SEV_COLOR[s].solid }}>
            <span className="sev-sum-num">{fmt(counts[s])}</span>
            <span className="sev-sum-label"><i style={{ background: SEV_COLOR[s].solid }} />{s}</span>
          </div>
        ))}
        <div className="sev-sum sev-sum-total"><span className="sev-sum-num">{fmt(im.total)}</span><span className="sev-sum-label">TOTAL · {scanner}</span></div>
      </div>

      <Card title={`Findings - ${im.name} · ${scanner}`} subtitle="this scanner's view only" pad={false}
        action={<button className="btn btn-mini"><Icon name="download" size={13} />CSV</button>}>
        <table className="tbl tbl-dense tbl-hover">
          <thead><tr><th>Vulnerability</th><th>Severity</th><th className="r">EPSS<span className="th-note">via Grype</span></th><th className="c">KEV</th><th>Package</th><th>Current</th><th>Fixed</th><th>State</th></tr></thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id} onClick={() => go("finding", f)}>
                <td className="mono-cell strong">{f.cve}</td>
                <td><Sev level={f.severity} /></td>
                <td className="r">{scanner === "Grype" ? <Epss v={f.epss} /> : <span className="muted-dash" title="EPSS enrichment arrives with Grype results only">-</span>}</td>
                <td className="c"><Kev on={f.kev} /></td>
                <td><span className="pkg">{f.pkg}<i className="pkg-type">{f.ptype}</i></span></td>
                <td className="mono-cell sm"><span className="ver-cur">{f.current}</span></td>
                <td className="mono-cell sm">{f.fixed ? <span className="ver-fix">{f.fixed}</span> : <span className="ver-none">no fix</span>}</td>
                <td><StateTag state={f.state} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

Object.assign(window, { Images, ImageDetail });
