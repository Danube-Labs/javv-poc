/* JAVV — All clusters: fleet-level rollup, one row per cluster */
function HealthTag({ health }) {
  const M = { healthy: ["Healthy", "health-ok"], degraded: ["Degraded", "health-deg"], stale: ["Sweep stale", "health-stale"], pending: ["First sweep pending", "health-pending"], ok: ["ok", "health-ok"], failing: ["failing", "health-deg"] };
  const [label, cls] = M[health] || [health, "health-stale"];
  return <span className={"health-tag " + cls}><i />{label}</span>;
}

function AllClusters({ go, setCluster }) {
  const cs = JAVV.clusters;
  const [scanner, setScanner] = useState("All scanners");
  const S = (n) => Math.round(n * SCANNER_FACTOR[scanner]);
  const tot = (k) => S(cs.reduce((a, c) => a + c[k], 0));
  const degraded = cs.filter((c) => c.health !== "healthy").length;
  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>All clusters</h1>
          <p className="screen-sub">Fleet rollup · <b>{cs.length}</b> clusters · {degraded ? <span className="deg-note">{degraded} need attention</span> : "all healthy"} · keyed on cluster_id</p>
        </div>
        <div className="screen-head-actions">
          <ScannerFilter value={scanner} onChange={setScanner} />
          <button className="btn btn-ghost"><Icon name="download" size={14} />Export CSV</button>
        </div>
      </div>

      <div className="fleet-kpis">
        {[["CRITICAL", "crit"], ["HIGH", "high"], ["MEDIUM", "med"], ["LOW", "low"]].map(([s, k]) => (
          <div className="hero-kpi" key={s} style={{ "--accent": CHART_SEV[s] }}>
            <span className="hero-kpi-num">{fmt(tot(k))}</span>
            <span className="hero-kpi-label">{s}</span>
            <span className="hero-kpi-sub">across the fleet</span>
          </div>
        ))}
        <div className="hero-kpi" style={{ "--accent": "#1F8E84" }}>
          <span className="hero-kpi-num">{cs.reduce((a, c) => a + c.images, 0)}</span>
          <span className="hero-kpi-label">IMAGES</span>
          <span className="hero-kpi-sub">{cs.reduce((a, c) => a + c.replicas, 0)} replicas at last sweep</span>
        </div>
      </div>

      <Card pad={false} className="fleet-card">
        <table className="tbl tbl-hover">
          <thead>
            <tr><th>Cluster</th><th>Health</th><th style={{ width: 170 }}>Severity mix</th><th className="r">Images</th><th>Scanners</th><th>Last sweep</th></tr>
          </thead>
          <tbody>
            {cs.map((c) => (
              <tr key={c.id} onClick={() => { setCluster && setCluster(c); go("overview"); }} title={`Open ${c.name} overview`}>
                <td>
                  <div className="cluster-cell">
                    <span className="cluster-glyph sm">{c.name[0].toUpperCase()}</span>
                    <div className="cluster-info"><span className="cluster-name">{c.name}</span><span className="cluster-id mono-cell">{c.id}</span></div>
                  </div>
                </td>
                <td><HealthTag health={c.health} /></td>
                <td>{c.images ? <MixBar crit={S(c.crit)} high={S(c.high)} med={S(c.med)} low={S(c.low)} /> : <span className="muted-dash">—</span>}</td>
                <td className="r">{c.images}</td>
                <td>
                  {Object.keys(c.scannerHealth).length ? (
                    <span className="scanner-stack">
                      {Object.entries(c.scannerHealth).map(([s, h]) => (
                        <span key={s} className="scanner-health" title={`${s}: ${h}`}>
                          <ScannerTag name={s} /><i className={"sc-dot " + (h === "ok" ? "sc-ok" : "sc-bad")} />
                        </span>
                      ))}
                    </span>
                  ) : <span className="muted-dash">—</span>}
                </td>
                <td><RelTime rel={c.sweepRel} abs={c.sweepAbs} className={c.health === "stale" ? "sweep-stale" : ""} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="fleet-note"><Icon name="layers" size={13} />Each cluster's scanner module pushes independently over HTTPS with its own API token — a cluster going quiet shows up here, not as missing data downstream.</p>
    </div>
  );
}

Object.assign(window, { AllClusters, HealthTag });
