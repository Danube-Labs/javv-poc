/* JAVV — Scanner status: ingest pipeline health, per scanner */
function ingestChartOption() {
  const s = JAVV.ingestSeries, f = JAVV.failedSeries;
  return {
    grid: { left: 44, right: 16, top: 16, bottom: 26 },
    tooltip: { trigger: "axis", backgroundColor: "#16232F", borderWidth: 0, textStyle: { color: "#F3EEE6", fontSize: 11 } },
    xAxis: { type: "category", data: s.days, boundaryGap: false, axisLine: { lineStyle: { color: "#E6DFD4" } }, axisLabel: { color: "#8C97A0", fontSize: 10, interval: 4 }, axisTick: { show: false } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#F0EBE2" } }, axisLabel: { color: "#8C97A0", fontSize: 10 } },
    series: [
      { name: "Trivy ingested", type: "line", smooth: true, symbol: "none", data: s.Trivy, lineStyle: { width: 2, color: "#1C7A70" }, itemStyle: { color: "#1C7A70" }, areaStyle: { color: "#1C7A70", opacity: 0.05 } },
      { name: "Grype ingested", type: "line", smooth: true, symbol: "none", data: s.Grype, lineStyle: { width: 2, color: "#5A4F9E" }, itemStyle: { color: "#5A4F9E" }, areaStyle: { color: "#5A4F9E", opacity: 0.05 } },
      { name: "Trivy failed", type: "bar", stack: "f", data: f.Trivy, itemStyle: { color: "#E2640F", opacity: 0.85 }, barWidth: "40%" },
      { name: "Grype failed", type: "bar", stack: "f", data: f.Grype, itemStyle: { color: "#C0271D", opacity: 0.85 }, barWidth: "40%" },
    ],
  };
}

function ScannerStatusCard({ s }) {
  const rate = ((s.ingested24h / (s.ingested24h + s.failed24h)) * 100).toFixed(1);
  return (
    <div className={"scan-card " + (s.health !== "ok" ? "scan-card-deg" : "")}>
      <div className="scan-card-head">
        <ScannerTag name={s.name} />
        <span className="mono-cell sm muted">v{s.version}</span>
        <HealthTag health={s.health === "ok" ? "healthy" : "degraded"} />
      </div>
      <div className="scan-stats">
        <div className="scan-stat"><span className="scan-num">{fmt(s.ingested24h)}</span><span className="scan-lbl">ingested · 24h</span></div>
        <div className="scan-stat"><span className={"scan-num " + (s.failed24h > 5 ? "scan-bad" : "")}>{s.failed24h}</span><span className="scan-lbl">failed · 24h</span></div>
        <div className="scan-stat"><span className="scan-num">{rate}%</span><span className="scan-lbl">success rate</span></div>
        <div className="scan-stat"><span className="scan-num">{s.queue}</span><span className="scan-lbl">in retry queue</span></div>
      </div>
      <div className="scan-meta">
        <span><em>Last run</em> <RelTime rel={s.lastRunRel} abs={s.lastRunAbs} /></span>
        <span><em>Vuln DB refreshed</em> <RelTime rel={s.dbRel} abs={s.dbAbs} /></span>
      </div>
    </div>
  );
}

function ScannerStatus({ go }) {
  const FIELDS = [
    { key: "scanner", label: "Scanner", values: ["Trivy", "Grype"], render: (k) => <ScannerTag name={k} />, valLabel: (k) => k },
    { key: "status", label: "Status", values: ["retrying", "dead-letter", "resolved"], render: (k) => <span className={"ingest-status ing-" + k}>{k}</span>, valLabel: (k) => k },
    { key: "stage", label: "Stage", values: [...new Set(JAVV.failedIngest.map((r) => r.stage))], render: (k) => <span className="mono-cell sm">{k}</span>, valLabel: (k) => k },
  ];
  const { sel, toggle, clearField, clearAll } = useFilters(FIELDS);
  const all = JAVV.failedIngest;
  const countVal = (field, val) => all.filter((r) => r[field] === val).length;
  const list = all.filter((r) =>
    (!sel.scanner.size || sel.scanner.has(r.scanner)) &&
    (!sel.status.size || sel.status.has(r.status)) &&
    (!sel.stage.size || sel.stage.has(r.stage))
  );

  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Scanner status</h1>
          <p className="screen-sub">Ingest pipeline health for <b>lorem-prod</b> · push is retried with backoff, permanent failures dead-letter</p>
        </div>
        <div className="screen-head-actions">
          <button className="btn btn-ghost" onClick={() => go("settings")}><Icon name="gear" size={14} />Scanner settings</button>
        </div>
      </div>

      <div className="scan-cards">
        {JAVV.scannerStatus.map((s) => <ScannerStatusCard key={s.name} s={s} />)}
      </div>

      <Card title="Ingested results over time" subtitle="lines: ingested per day · bars: failed pushes" className="scan-chart-card">
        <Chart option={ingestChartOption()} height={250} />
        <div className="legend-row">
          <span className="lg"><i style={{ background: "#1C7A70" }} />Trivy ingested</span>
          <span className="lg"><i style={{ background: "#5A4F9E" }} />Grype ingested</span>
          <span className="lg"><i style={{ background: "#E2640F" }} />Trivy failed</span>
          <span className="lg"><i style={{ background: "#C0271D" }} />Grype failed</span>
        </div>
      </Card>

      <div style={{ marginTop: 16 }}>
        <Card title="Failed ingests" subtitle="most recent first · retried with backoff + jitter" pad={false}
          action={<FilterBar fields={FIELDS} sel={sel} toggle={toggle} clearField={clearField} clearAll={clearAll} countVal={countVal} />}>
          <table className="tbl tbl-dense">
            <thead><tr><th>When</th><th>Scanner</th><th>Image</th><th>Stage</th><th>Error</th><th className="c">Retries</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {list.map((r, i) => (
                <tr key={i}>
                  <td><RelTime rel={r.rel} abs={r.abs} /></td>
                  <td><ScannerTag name={r.scanner} /></td>
                  <td className="mono-cell sm">{r.image}</td>
                  <td className="mono-cell sm muted">{r.stage}</td>
                  <td className="wrap-cell">{r.error}</td>
                  <td className="c mono-cell sm">{r.retries}</td>
                  <td><span className={"ingest-status ing-" + r.status}>{r.status}</span></td>
                  <td className="c">{r.status === "dead-letter" && <button className="btn btn-mini">Retry</button>}</td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr><td colSpan={8} className="empty-row">No failed ingests match. <button className="link-btn" onClick={clearAll}>Clear all</button></td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { ScannerStatus });
