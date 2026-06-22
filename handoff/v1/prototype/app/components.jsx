/* JAVV shared UI - exported to window for cross-file use. */
const { useState, useEffect, useRef, useMemo } = React;

/* ---------- severity palette (DATA only - firewalled from brand coral) ---------- */
const SEV_COLOR = {
  CRITICAL: { fg: "#B5231A", bg: "#FBE7E4", line: "#E7C0bb", solid: "#C0271D" },
  HIGH:     { fg: "#C2540D", bg: "#FCEBDD", line: "#EDD0B6", solid: "#E2640F" },
  MEDIUM:   { fg: "#9A6B05", bg: "#FBF1D6", line: "#EBDDAE", solid: "#C68A12" },
  LOW:      { fg: "#2F6E96", bg: "#E4F0F6", line: "#C2DCE8", solid: "#3D7DA6" },
  UNKNOWN:  { fg: "#5B6770", bg: "#ECEDEE", line: "#D8DCDF", solid: "#74808A" },
};
const CHART_SEV = { CRITICAL: "#C0271D", HIGH: "#E2640F", MEDIUM: "#C68A12", LOW: "#3D7DA6", UNKNOWN: "#9AA3AA" };
const fmt = (n) => (n == null ? "-" : n.toLocaleString("en-US"));

/* ---------- brand mark (inline, from approved icon.svg) ---------- */
function BrandIcon({ size = 28 }) {
  const uid = useMemo(() => "m" + Math.random().toString(36).slice(2, 7), []);
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="javv" style={{ display: "block", flex: "none" }}>
      <defs>
        <linearGradient id={`sky${uid}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#F7B57E" /><stop offset="1" stopColor="#EC7E54" /></linearGradient>
        <linearGradient id={`riv${uid}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#FCE7C1" /><stop offset="1" stopColor="#F4A368" /></linearGradient>
        <clipPath id={`lens${uid}`}><circle cx="27" cy="26" r="13" /></clipPath>
      </defs>
      <rect x="0" y="0" width="64" height="64" rx="16" fill="#16232F" />
      <line x1="30" y1="29" x2="51" y2="50" stroke="#F4A368" strokeWidth="6.6" strokeLinecap="round" />
      <g clipPath={`url(#lens${uid})`}>
        <rect x="13" y="12" width="28" height="14.4" fill={`url(#sky${uid})`} />
        <rect x="13" y="26.4" width="28" height="13.6" fill="#21384A" />
        <circle cx="27" cy="21" r="4.4" fill="#FCE7C1" />
        <path d="M13 26.4 Q20 23.8 27 25.6 Q34 27.2 41 24.8 L41 27.2 L13 27.2 Z" fill="#C76A55" opacity="0.55" />
        <path d="M26.5 27.2 C26 30 23.5 31.4 24 34 C24.4 37 24.2 38.8 25.2 40.6 L30.8 40.6 C31.6 38.6 28 37 27.5 34 C27 31 29 30 28.5 27.2 Z" fill={`url(#riv${uid})`} />
      </g>
      <circle cx="27" cy="26" r="13" fill="none" stroke="#F4A368" strokeWidth="3.3" />
    </svg>
  );
}

/* ---------- severity chip ---------- */
function Sev({ level, solid = false, dot = true }) {
  const c = SEV_COLOR[level] || SEV_COLOR.UNKNOWN;
  if (solid) {
    return <span className="sev sev-solid" style={{ background: c.solid }}>{level}</span>;
  }
  return (
    <span className="sev" style={{ background: c.bg, color: c.fg, borderColor: c.line }}>
      {dot && <i className="sev-dot" style={{ background: c.solid }} />}{level}
    </span>
  );
}

/* ---------- KEV / EPSS / state pills ---------- */
function Kev({ on }) {
  if (!on) return <span className="muted-dash">-</span>;
  return <span className="kev-tag">KEV</span>;
}
function Epss({ v }) {
  if (v == null) return <span className="muted-dash">-</span>;
  const pct = Math.round(v * 100);
  const hot = v >= 0.7, warm = v >= 0.3;
  return (
    <span className="epss">
      <span className="epss-bar"><i style={{ width: pct + "%", background: hot ? "#C0271D" : warm ? "#E2640F" : "#9AA3AA" }} /></span>
      <span className="epss-num">{pct}%</span>
    </span>
  );
}
const STATE_STYLE = {
  open: { label: "Open", cls: "st-open" },
  stale: { label: "Stale", cls: "st-stale" },
  acknowledged: { label: "Acknowledged", cls: "st-ack" },
  resolved: { label: "Resolved", cls: "st-res" },
};
function StateTag({ state }) {
  const s = STATE_STYLE[state] || STATE_STYLE.open;
  return <span className={"state-tag " + s.cls}>{s.label}</span>;
}
function ScannerTag({ name }) {
  return <span className={"scanner-tag sc-" + name.toLowerCase()}>{name}</span>;
}
function Sla({ days, overdue }) {
  if (overdue) return <span className="sla sla-over">overdue</span>;
  const tight = days <= 2;
  return <span className={"sla " + (tight ? "sla-tight" : "")}>{days}d</span>;
}

/* ---------- card ---------- */
function Card({ title, action, children, pad = true, className = "", subtitle }) {
  return (
    <section className={"card " + className}>
      {title && (
        <header className="card-head">
          <div>
            <h3>{title}</h3>
            {subtitle && <span className="card-sub">{subtitle}</span>}
          </div>
          {action}
        </header>
      )}
      <div className={pad ? "card-body" : ""}>{children}</div>
    </section>
  );
}

/* ---------- ECharts wrapper ---------- */
function Chart({ option, height = 240, className = "" }) {
  const ref = useRef(null);
  const inst = useRef(null);
  useEffect(() => {
    if (!ref.current || typeof echarts === "undefined") return;
    inst.current = echarts.init(ref.current, null, { renderer: "svg" });
    const ro = new ResizeObserver(() => inst.current && inst.current.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); inst.current && inst.current.dispose(); };
  }, []);
  useEffect(() => { inst.current && inst.current.setOption(option, true); }, [option]);
  return <div ref={ref} className={"chart " + className} style={{ height }} />;
}

/* ---------- small bits ---------- */
function Spark({ data, color = "#EC7E54", height = 30, width = 92 }) {
  const max = Math.max(...data), min = Math.min(...data);
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((d - min) / (max - min || 1)) * (height - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={width} height={height} className="spark">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function Pill({ children, active, onClick, count }) {
  return (
    <button className={"pill " + (active ? "pill-on" : "")} onClick={onClick}>
      {children}{count != null && <span className="pill-count">{count}</span>}
    </button>
  );
}

function RelTime({ rel, abs, className = "" }) {
  return <span className={"mono-cell sm muted " + className} title={abs}>{rel}</span>;
}

function Pager({ total, page, setPage, per, setPer, sizes = [10, 25, 50] }) {
  const pages = Math.ceil(total / per) || 1;
  const start = page * per + 1, end = Math.min((page + 1) * per, total);
  return (
    <div className="pager">
      <span className="pager-info">{total ? `Showing ${start}–${end} of ${fmt(total)}` : "No results"}</span>
      <div className="pager-right">
        <label className="pager-size">Rows per page
          <select value={per} onChange={(e) => { setPer(+e.target.value); setPage(0); }}>
            {sizes.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <div className="pager-btns">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</button>
          {Array.from({ length: Math.min(pages, 5) }).map((_, i) => (
            <button key={i} className={i === page ? "pg-on" : ""} onClick={() => setPage(i)}>{i + 1}</button>
          ))}
          {pages > 5 && <span className="pg-ell">… {pages}</span>}
          <button disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
    </div>
  );
}

function Avatar({ initials, tone, size = 22 }) {
  return <span className="av" style={{ background: tone || "#74808A", width: size, height: size, fontSize: Math.round(size * 0.4) }}>{initials}</span>;
}

function MiniBar({ crit, high, med, low }) {
  const total = crit + high + med + low || 1;
  const seg = (v, c) => v ? <i style={{ width: (v / total * 100) + "%", background: c }} /> : null;
  return (
    <span className="mini-bar" title={`C ${crit} · H ${high} · M ${med} · L ${low}`}>
      {seg(crit, CHART_SEV.CRITICAL)}{seg(high, CHART_SEV.HIGH)}{seg(med, CHART_SEV.MEDIUM)}{seg(low, CHART_SEV.LOW)}
    </span>
  );
}

/* bar + readable per-severity counts - use in tables instead of hover-only MiniBar */
function MixBar({ crit, high, med, low }) {
  return (
    <div className="mix-cell">
      <MiniBar crit={crit} high={high} med={med} low={low} />
      <span className="mix-nums">
        <b style={{ color: SEV_COLOR.CRITICAL.fg }}>{fmt(crit)}</b>
        <b style={{ color: SEV_COLOR.HIGH.fg }}>{fmt(high)}</b>
        <b style={{ color: SEV_COLOR.MEDIUM.fg }}>{fmt(med)}</b>
        <b style={{ color: SEV_COLOR.LOW.fg }}>{fmt(low)}</b>
      </span>
    </div>
  );
}

/* segmented scanner facet for overview screens */
function ScannerFilter({ value, onChange }) {
  return (
    <div className="seg scanner-filter">
      {["All scanners", "Trivy", "Grype"].map((v) => (
        <button key={v} className={"seg-opt " + (value === v ? "seg-on" : "")} onClick={() => onChange(v)}>
          {v === "All scanners" ? v : <ScannerTag name={v} />}
        </button>
      ))}
    </div>
  );
}
const SCANNER_FACTOR = { "All scanners": 1, Trivy: 0.53, Grype: 0.47 };

/* first-run empty state - shown when a cluster's first sweep hasn't landed yet */
function FirstRun({ go, clusterName, what = "findings" }) {
  return (
    <div className="screen">
      <div className="firstrun">
        <div className="firstrun-icon"><Icon name="clock" size={26} /></div>
        <h2>Waiting for the first sweep</h2>
        <p>The scanner module on <b>{clusterName}</b> is installed and connected, but no {what} have been pushed yet. Results appear here as soon as the first sweep completes.</p>
        <div className="firstrun-meta"><span className="sweep-dot" />Module connected · push token verified · first sweep scheduled 07:00</div>
        <div className="firstrun-actions">
          <button className="btn btn-primary" onClick={() => go("scanstatus")}>View scanner status</button>
          <button className="btn btn-ghost" onClick={() => go("allclusters")}>All clusters</button>
        </div>
      </div>
    </div>
  );
}

function Icon({ name, size = 16 }) {
  const paths = {
    grid: "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
    list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    cube: "M21 7.5l-9-5-9 5 9 5 9-5zM3 7.5v9l9 5 9-5v-9M12 12.5v9",
    shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z",
    check: "M5 12l4 4L19 7",
    clock: "M12 7v5l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
    search: "M21 21l-4.3-4.3M11 18a7 7 0 100-14 7 7 0 000 14z",
    chevron: "M9 6l6 6-6 6",
    download: "M12 3v12m0 0l-4-4m4 4l4-4M4 21h16",
    filter: "M3 5h18l-7 8v6l-4-2v-4z",
    external: "M14 4h6v6M20 4l-9 9M19 13v6a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1h6",
    bell: "M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0",
    alert: "M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
    bookmark: "M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2v16z",
    columns: "M9 3v18M15 3v18M3 5a2 2 0 012-2h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5z",
    pulse: "M22 12h-4l-3 9L9 3l-3 9H2",
    award: "M12 15a7 7 0 100-14 7 7 0 000 14zM8.21 13.89L7 23l5-3 5 3-1.21-9.12",
    calendar: "M8 2v4M16 2v4M3 9h18M5 4h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z",
    layers: "M12 2l9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5",
    arrowback: "M19 12H5M12 19l-7-7 7-7",
    gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 008 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H2a2 2 0 010-4h.09A1.65 1.65 0 004.6 8a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V2a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H22a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z",
    plus: "M12 5v14M5 12h14",
    trash: "M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14",
    dot: "",
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none" }}>
      <path d={paths[name] || ""} />
    </svg>
  );
}

Object.assign(window, {
  useState, useEffect, useRef, useMemo,
  SEV_COLOR, CHART_SEV, fmt,
  BrandIcon, Sev, Kev, Epss, StateTag, ScannerTag, Sla, Card, Chart, Spark, Pill, Icon, Avatar, RelTime, Pager, MiniBar, MixBar, ScannerFilter, SCANNER_FACTOR, FirstRun,
});
