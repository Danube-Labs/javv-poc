/* JAVV — Overview dashboard */
function KpiStrip({ go, S }) {
  const t = JAVV.severityTotals, n = JAVV.new30d;
  const order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
  const fixable = JAVV.findings.filter((f) => f.fixed).length;
  const fixPct = Math.round(fixable / JAVV.findings.length * 100);
  return (
    <div className="kpi-strip">
      {order.map((s) => {
        const c = SEV_COLOR[s];
        return (
          <div className="kpi kpi-link" key={s} style={{ "--accent": c.solid }} onClick={() => go("findings", { filters: { severity: [s] } })} title={`Open findings filtered to ${s}`}>
            <div className="kpi-top">
              <span className="kpi-label"><i className="kpi-dot" style={{ background: c.solid }} />{s}</span>
              <span className="kpi-new">+{fmt(S(n[s]))} <em>30d</em></span>
            </div>
            <div className="kpi-num">{fmt(S(t[s]))}</div>
            <Spark data={JAVV.severitySeries[s].map(S)} color={c.solid} width={150} height={26} />
          </div>
        );
      })}
      <div className="kpi kpi-link kpi-fix" style={{ "--accent": "#1F8E84" }} onClick={() => go("findings", { filters: { attr: ["hasfix"] } })} title="Open findings with a fix available">
        <div className="kpi-top">
          <span className="kpi-label"><i className="kpi-dot" style={{ background: "#1F8E84" }} />FIX AVAILABLE</span>
        </div>
        <div className="kpi-num">{fixPct}%</div>
        <span className="kpi-fix-sub">{fmt(S(fixable))} findings patchable today</span>
      </div>
    </div>
  );
}

function severityOverTimeOption(S) {
  const s = JAVV.severitySeries;
  const mk = (k) => ({
    name: k, type: "line", smooth: true, symbol: "none", data: s[k].map(S),
    lineStyle: { width: 2, color: CHART_SEV[k] }, itemStyle: { color: CHART_SEV[k] },
    areaStyle: { color: CHART_SEV[k], opacity: 0.06 },
  });
  return {
    grid: { left: 44, right: 16, top: 16, bottom: 26 },
    legend: { show: false },
    tooltip: { trigger: "axis", backgroundColor: "#16232F", borderWidth: 0, textStyle: { color: "#F3EEE6", fontSize: 11 } },
    xAxis: { type: "category", data: s.days, boundaryGap: false, axisLine: { lineStyle: { color: "#E6DFD4" } }, axisLabel: { color: "#8C97A0", fontSize: 10, interval: 4 }, axisTick: { show: false } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#F0EBE2" } }, axisLabel: { color: "#8C97A0", fontSize: 10 } },
    series: ["MEDIUM", "HIGH", "LOW", "CRITICAL"].map(mk),
  };
}

function packageDonutOption() {
  const colors = ["#1F8E84", "#2FA89C", "#7CC4BC", "#A7D6D0", "#C9E5E1", "#E0EFD9", "#F4D9A8", "#F2B98A", "#EC9F84"];
  return {
    tooltip: { trigger: "item", backgroundColor: "#16232F", borderWidth: 0, textStyle: { color: "#F3EEE6", fontSize: 11 }, formatter: "{b}: {d}%" },
    legend: { show: false },
    series: [{
      type: "pie", radius: ["54%", "82%"], center: ["50%", "52%"], avoidLabelOverlap: true,
      label: { show: false }, labelLine: { show: false },
      data: JAVV.packageTypes.map((p, i) => ({ value: p.value, name: p.name, itemStyle: { color: colors[i % colors.length], borderColor: "#fff", borderWidth: 1.5 } })),
    }],
  };
}

function publishedBarsOption(S) {
  return {
    grid: { left: 34, right: 12, top: 12, bottom: 24 },
    tooltip: { trigger: "axis", backgroundColor: "#16232F", borderWidth: 0, textStyle: { color: "#F3EEE6", fontSize: 11 } },
    xAxis: { type: "category", data: JAVV.severitySeries.days, axisLine: { lineStyle: { color: "#E6DFD4" } }, axisLabel: { color: "#8C97A0", fontSize: 10, interval: 5 }, axisTick: { show: false } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#F0EBE2" } }, axisLabel: { color: "#8C97A0", fontSize: 10 } },
    series: [{ type: "bar", data: JAVV.publishedSeries.map(S), itemStyle: { color: "#2FA89C", borderRadius: [2, 2, 0, 0] }, barWidth: "55%" }],
  };
}

function Overview({ go, cluster }) {
  const [scanner, setScanner] = useState("All scanners");
  const S = (n) => Math.round(n * SCANNER_FACTOR[scanner]);
  const cname = cluster ? cluster.name : "lorem-prod";
  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Overview</h1>
          <p className="screen-sub">Current state across <b>{cname}</b> · 13 workloads · last sweep <span title="Jun 12, 07:00">5h ago</span></p>
        </div>
        <div className="screen-head-actions">
          <ScannerFilter value={scanner} onChange={setScanner} />
          <button className="btn btn-ghost"><Icon name="download" size={14} />Export CSV</button>
          <button className="btn btn-primary" onClick={() => go("findings", { filters: { severity: ["CRITICAL"] } })}>Triage critical <Icon name="chevron" size={14} /></button>
        </div>
      </div>

      <KpiStrip go={go} S={S} />

      <div className="grid grid-2-1" style={{ marginTop: 16 }}>
        <Card title="Vulnerabilities over time" subtitle="by severity · last 30 days" action={<span className="card-tag">{scanner === "All scanners" ? "all scanners" : scanner + " only"}</span>}>
          <Chart option={severityOverTimeOption(S)} height={250} />
          <div className="legend-row">
            {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
              <span className="lg" key={s}><i style={{ background: CHART_SEV[s] }} />{s} <b>{fmt(S(JAVV.severityTotals[s]))}</b></span>
            ))}
          </div>
        </Card>
        <Card title="Package type" subtitle="share of findings">
          <Chart option={packageDonutOption()} height={188} />
          <div className="donut-legend">
            {JAVV.packageTypes.slice(0, 6).map((p, i) => (
              <span key={p.name}><i style={{ background: ["#1F8E84", "#2FA89C", "#7CC4BC", "#A7D6D0", "#C9E5E1", "#E0EFD9"][i] }} />{p.name} <b>{p.value}%</b></span>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-1-1" style={{ marginTop: 16 }}>
        <Card title="Per namespace" subtitle="k8s-runtime · top 10" action={<button className="btn btn-mini" onClick={() => go("images")}>View inventory</button>}>
          <table className="tbl tbl-hover">
            <thead><tr><th>Namespace</th><th style={{ width: 170 }}>Severity mix</th></tr></thead>
            <tbody>
              {JAVV.namespaces.map((n) => (
                <tr key={n.ns} onClick={() => go("findings", { filters: { ns: [n.ns] } })} title={`Open findings in ${n.ns}`}>
                  <td className="mono-cell">{n.ns}</td>
                  <td><MixBar crit={S(n.crit)} high={S(n.high)} med={S(n.med)} low={S(n.low)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Top components" subtitle="by unique vulnerabilities">
          <table className="tbl tbl-hover">
            <thead><tr><th>Component</th><th className="r">Avg</th><th className="r">Min</th><th className="r">Max</th><th className="r">Last</th></tr></thead>
            <tbody>
              {JAVV.topComponents.map((c) => (
                <tr key={c.name}><td className="mono-cell">{c.name}</td><td className="r">{fmt(S(c.avg))}</td><td className="r muted">{fmt(S(c.min))}</td><td className="r muted">{fmt(S(c.max))}</td><td className="r"><b>{fmt(S(c.last))}</b></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid grid-1-1" style={{ marginTop: 16 }}>
        <Card title="Newly published" subtitle="CVEs hitting the fleet · last 30 days">
          <Chart option={publishedBarsOption(S)} height={190} />
        </Card>
        <Card title="Language-specific binaries" subtitle="unique vulnerabilities by target">
          <table className="tbl">
            <thead><tr><th>Target / path</th><th className="r">Vulns</th></tr></thead>
            <tbody>
              {JAVV.languageBinaries.map((l) => (
                <tr key={l.path}><td className="mono-cell">{l.path}</td><td className="r"><b>{fmt(S(l.count))}</b></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { Overview });
