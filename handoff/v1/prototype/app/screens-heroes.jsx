/* JAVV — Heroes / activity (most vulns solved, leaderboard, audit feed) */
function resolvedOverTimeOption(dayCount) {
  const s = JAVV.resolvedSeries;
  const n = Math.min(s.days.length, Math.max(1, Math.ceil(dayCount || 30)));
  const sl = (arr) => arr.slice(arr.length - n);
  const days = sl(s.days);
  const mk = (k) => ({
    name: k, type: "bar", stack: "r", data: sl(s[k]),
    itemStyle: { color: CHART_SEV[k] }, barWidth: "62%",
    emphasis: { focus: "series" },
  });
  return {
    grid: { left: 34, right: 12, top: 14, bottom: 24 },
    tooltip: { trigger: "axis", backgroundColor: "#16232F", borderWidth: 0, textStyle: { color: "#F3EEE6", fontSize: 11 } },
    xAxis: { type: "category", data: days, axisLine: { lineStyle: { color: "#E6DFD4" } }, axisLabel: { color: "#8C97A0", fontSize: 10, interval: n > 14 ? 5 : 1 }, axisTick: { show: false } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#F0EBE2" } }, axisLabel: { color: "#8C97A0", fontSize: 10 } },
    series: ["MEDIUM", "HIGH", "LOW", "CRITICAL"].map(mk),
  };
}

function HeroAvatar({ h, size = 38 }) {
  return <span className="hero-av" style={{ background: h.tone, width: size, height: size, fontSize: size * 0.36 }}>{h.initials}</span>;
}

function PodiumCard({ h, rank }) {
  const total = h.crit + h.high + h.med + h.low || 1;
  const seg = (v, c) => v ? <i style={{ width: (v / total * 100) + "%", background: c }} /> : null;
  return (
    <div className={"podium podium-" + rank}>
      <div className="podium-rank">{rank}</div>
      <HeroAvatar h={h} size={rank === 1 ? 56 : 46} />
      <div className="podium-name">{h.name}</div>
      <div className="podium-role">{h.role}</div>
      <div className="podium-num">{fmt(h.resolved)}<em>resolved</em></div>
      <span className="mini-bar podium-bar">
        {seg(h.crit, CHART_SEV.CRITICAL)}{seg(h.high, CHART_SEV.HIGH)}{seg(h.med, CHART_SEV.MEDIUM)}{seg(h.low, CHART_SEV.LOW)}
      </span>
      <div className="podium-meta">
        <span><b>{h.slaHit}%</b> SLA</span>
        <span><b>{h.medianDays}d</b> median</span>
        {h.streak >= 5 && <span className="podium-streak"><i className="streak-dot" />{h.streak}d streak</span>}
      </div>
    </div>
  );
}

function Heroes({ go, timeRange }) {
  const tr = timeRange || { label: "Last 30 days", days: 30 };
  const factor = Math.max(0.01, tr.days / 30);
  const S = (n) => Math.max(0, Math.round(n * factor));
  const range = tr.label.toLowerCase().startsWith("last") ? tr.label.toLowerCase() : tr.label;
  const st = JAVV.heroStats;
  const heroes = JAVV.heroes.map((h) => ({ ...h, resolved: S(h.resolved), acknowledged: S(h.acknowledged), crit: S(h.crit), high: S(h.high), med: S(h.med), low: S(h.low) }));
  const podium = [heroes[1], heroes[0], heroes[2]]; // 2 · 1 · 3 visual order
  const podiumRanks = [2, 1, 3];
  const kpis = [
    { label: "RESOLVED", sub: range, num: fmt(S(st.resolved30d)), accent: "#2E7D4F" },
    { label: "ACKNOWLEDGED", sub: "with justification", num: fmt(S(st.acknowledged30d)), accent: "#3D7DA6" },
    { label: "MEDIAN TIME-TO-RESOLVE", sub: "across severities", num: st.medianDays + "d", accent: "#1F8E84" },
    { label: "SLA MET", sub: "of closed findings", num: st.slaHit + "%", accent: "#C2540D" },
    { label: "CRITICAL CLEARED", sub: range, num: fmt(S(st.critCleared)), accent: "#C0271D" },
  ];

  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h1>Contributors</h1>
          <p className="screen-sub">Who's clearing the backlog · resolved &amp; acknowledged findings, by person · <b>{range}</b></p>
        </div>
        <div className="screen-head-actions">
          <button className="btn btn-ghost"><Icon name="download" size={14} />Export CSV</button>
        </div>
      </div>

      <div className="hero-note">
        <Icon name="layers" size={13} />
        Derived from the audit trail. Trend depth lands with historical scan series — current-state MVP counts decisions, not scan-over-scan deltas.
      </div>

      <div className="hero-kpis">
        {kpis.map((k) => (
          <div className="hero-kpi" key={k.label} style={{ "--accent": k.accent }}>
            <span className="hero-kpi-num">{k.num}</span>
            <span className="hero-kpi-label">{k.label}</span>
            <span className="hero-kpi-sub">{k.sub}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-2-1" style={{ marginTop: 16, alignItems: "start" }}>
        <div className="stack">
          <Card title="Top contributors" subtitle={"most findings resolved · " + range}>
            <div className="podiums">
              {podium.map((h, i) => <PodiumCard key={h.name} h={h} rank={podiumRanks[i]} />)}
            </div>
          </Card>

          <Card title="Leaderboard" subtitle="all contributors" pad={false}>
            <table className="tbl tbl-hover">
              <thead>
                <tr><th>#</th><th>Person</th><th className="r">Resolved</th><th className="r">Ack.</th><th style={{ width: 120 }}>Severity mix</th><th className="r">Median</th><th className="r">SLA</th><th>Pace</th></tr>
              </thead>
              <tbody>
                {heroes.map((h, i) => {
                  const total = h.crit + h.high + h.med + h.low || 1;
                  const seg = (v, c) => v ? <i style={{ width: (v / total * 100) + "%", background: c }} /> : null;
                  return (
                    <tr key={h.name}>
                      <td className="rank-cell">{i + 1}</td>
                      <td>
                        <div className="lb-person"><HeroAvatar h={h} size={30} /><div className="lb-id"><span className="lb-name">{h.name}</span><span className="lb-role">{h.role}</span></div></div>
                      </td>
                      <td className="r strong">{fmt(h.resolved)}</td>
                      <td className="r muted">{fmt(h.acknowledged)}</td>
                      <td><span className="mini-bar">{seg(h.crit, CHART_SEV.CRITICAL)}{seg(h.high, CHART_SEV.HIGH)}{seg(h.med, CHART_SEV.MEDIUM)}{seg(h.low, CHART_SEV.LOW)}</span></td>
                      <td className="r mono-cell sm">{h.medianDays}d</td>
                      <td className="r"><span className={"sla-pct " + (h.slaHit >= 88 ? "good" : h.slaHit >= 80 ? "ok" : "low")}>{h.slaHit}%</span></td>
                      <td><Spark data={h.trend} color={h.tone} width={70} height={24} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>

          <Card title="Resolved over time" subtitle={"by severity · " + range}>
            <Chart option={resolvedOverTimeOption(tr.days)} height={200} />
            <div className="legend-row">
              {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((sv) => (
                <span className="lg" key={sv}><i style={{ background: CHART_SEV[sv] }} />{sv}</span>
              ))}
            </div>
          </Card>
        </div>

        <Card title="Recent activity" subtitle="audit trail · live" action={<button className="btn btn-mini" onClick={() => go("approvals")}>Approval list</button>}>
          <div className="feed">
            {JAVV.activity.map((a, i) => (
              <div className="feed-item" key={i} onClick={() => go("finding", { cve: a.cve, severity: a.sev })}>
                <HeroAvatar h={a} size={30} />
                <div className="feed-body">
                  <div className="feed-line">
                    <b>{a.who.split(" ")[0]}</b>
                    <span className={"feed-act act-" + a.act}>{a.act}</span>
                    <span className="feed-cve mono-cell">{a.cve}</span>
                    <Sev level={a.sev} dot={false} />
                  </div>
                  <div className="feed-note">{a.note}</div>
                </div>
                <span className="feed-when">{a.when}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { Heroes });
