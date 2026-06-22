/* JAVV — Running images inventory + image detail (Trivy/Grype scanner dropdown) */
function Images({ go, cluster, atT, atTLabel }) {
  const imgs = JAVV.images;
  const [q, setQ] = useState("");
  const [exp, setExp] = useState(false);
  const scannerSilent = cluster && (cluster.health === "degraded" || cluster.health === "stale");
  const incomplete = cluster && cluster.health === "degraded";
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
          <Gate cap="can_export" disable><button className="btn btn-ghost" disabled={!can("can_export")} onClick={() => setExp(true)}><Icon name="download" size={14} />Export CSV</button></Gate>
        </div>
      </div>

      {atT ? (
        <div className="notlive-banner nlb-hist"><Icon name="rewind" size={14} /><span>Inventory <b>as scanned at {atTLabel}</b> — from the latest complete inventory run ≤ that moment. Not live deployment state.</span></div>
      ) : incomplete ? (
        <div className="notlive-banner nlb-warn"><Icon name="alert" size={14} /><span>Showing the <b>last complete inventory</b> ({cluster.sweepAbs}); the most recent run didn't finish — partial results are never shown as live.</span></div>
      ) : scannerSilent ? (
        <div className="notlive-banner nlb-warn"><Icon name="clock" size={14} /><span>Inventory as of <b>{cluster.sweepAbs}</b>; scanner silent since then — this is the last known snapshot, not live state.</span></div>
      ) : null}

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
                  <th className="r">Vulns<span className="th-note">Trivy / Grype · never summed</span></th><th style={{ width: 150 }}>Severity mix</th><th>Scanners</th><th>Last seen</th>
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
                    <td className="r"><CountDisagree trivy={im.trivyCount} grype={im.grypeCount} delta={im.countDelta} /></td>
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
      {exp && <ExportDialog scope={`Running images · ${list.length} of ${imgs.length}`} rows={list.length} onClose={() => setExp(false)} />}
    </div>
  );
}

function ImageDetail({ go, image, atT, atTLabel }) {
  const im = image && image.name ? image : JAVV.images[0];
  const [scanner, setScanner] = useState(im.scanners[0]);
  const [open, setOpen] = useState(false);
  const hist = JAVV.digestHistory;
  // when time-traveling far enough back, this digest wasn't scanned yet
  const notScannedYet = atT && atTLabel && atTLabel.includes("30 days");

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
            <p className="digest-line mono-cell sm"><Icon name="key" size={11} />{hist.digests[0].digest}<i className="digest-note">identity is the content digest — repo:tag is just a handle</i></p>
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
                    <ScannerTag name={s} /><span className="dd-img">{im.name} — {s}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* two distinct questions, two answers */}
      <div className="two-q">
        <div className="tq-card">
          <span className="tq-label"><Icon name="cube" size={12} />Was it running {atT ? "at " + atTLabel : "now"}?</span>
          <span className="tq-ans">{notScannedYet ? <span className="muted">Not in inventory then</span> : <span className="run-on"><i className="run-dot" />Yes · {im.replicas} replicas</span>}</span>
          <span className="tq-src">runtime inventory</span>
        </div>
        <div className="tq-card">
          <span className="tq-label"><Icon name="shield" size={12} />What did a scan find?</span>
          <span className="tq-ans">{notScannedYet ? <span className="muted">Not yet scanned then</span> : <span><b className="mono-cell">{fmt(im.total)}</b> vulns · {scanner}</span>}</span>
          <span className="tq-src">as-scanned, not as-running</span>
        </div>
      </div>

      {/* per-digest build sub-timeline */}
      <Card title="Build history" subtitle="a rebuilt tag is a NEW digest — sub-timelines, never a silent gap" className="mt0">
        <div className="digest-tl">
          {hist.digests.map((d, i) => (
            <div key={d.digest} className={"digest-row " + (d.running ? "digest-running" : "")}>
              <span className="digest-dot" />
              <span className="mono-cell sm strong">{d.digest}</span>
              <span className="digest-range mono-cell sm">{d.from} → {d.to}</span>
              <span className="digest-counts mono-cell sm"><i style={{ color: SEV_COLOR.CRITICAL.fg }}>{d.crit}C</i> <i style={{ color: SEV_COLOR.HIGH.fg }}>{d.high}H</i></span>
              {d.running ? <span className="digest-badge digest-now">running now</span> : <span className="digest-marker"><Icon name="info" size={11} />image build changed here</span>}
            </div>
          ))}
        </div>
      </Card>

      {notScannedYet ? (
        <Card className="mt16"><div className="empty-scan"><Icon name="rescan" size={28} /><h3>Not yet scanned then</h3><p>No committed scan of this digest exists at or before {atTLabel}. Reach is bounded by this cluster's retained data.</p></div></Card>
      ) : (
      <>
      <div className="sev-summary">
        {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
          <div className="sev-sum" key={s} style={{ "--accent": SEV_COLOR[s].solid }}>
            <span className="sev-sum-num">{fmt(counts[s])}</span>
            <span className="sev-sum-label"><i style={{ background: SEV_COLOR[s].solid }} />{s}</span>
          </div>
        ))}
        <div className="sev-sum sev-sum-total"><span className="sev-sum-num">{fmt(im.total)}</span><span className="sev-sum-label">TOTAL · {scanner}</span></div>
      </div>

      <Card title={`Findings — ${im.name} · ${scanner}`} subtitle="this scanner's view only" pad={false}
        action={<button className="btn btn-mini"><Icon name="download" size={13} />CSV</button>}>
        <table className="tbl tbl-dense tbl-hover">
          <thead><tr><th>Vulnerability</th><th>Severity<span className="th-note">verbatim {scanner} word</span></th><th className="r">EPSS<span className="th-note">via Grype</span></th><th className="c">KEV</th><th>Package</th><th>Current</th><th>Fixed</th><th>State</th></tr></thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id} onClick={() => go("finding", f)}>
                <td className="mono-cell strong">{f.cve}</td>
                <td><Sev level={f.severity} /></td>
                <td className="r">{scanner === "Grype" ? <Epss v={f.epss} /> : <span className="muted-dash" title="EPSS enrichment arrives with Grype results only">—</span>}</td>
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
      </>
      )}
    </div>
  );
}

Object.assign(window, { Images, ImageDetail });
