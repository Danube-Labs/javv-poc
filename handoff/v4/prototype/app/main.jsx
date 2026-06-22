/* JAVV - app shell: sidebar, topbar (working search + notifications), cluster switcher, router */
function Sidebar({ route, go }) {
  const groups = [
    { label: "Monitor", items: [["allclusters", "All clusters", "layers"], ["overview", "Overview", "grid"], ["findings", "Findings", "list"], ["views", "Saved views", "bookmark"], ["scanstatus", "Scanner status", "pulse"]] },
    { label: "Inventory", items: [["images", "Running images", "cube"]] },
    { label: "Audit", items: [["approvals", "Approval list", "shield"], ["audit", "Audit log", "clock"]] },
    { label: "Insights", items: [["heroes", "Contributors", "award"]] },
    { label: "Configure", items: [["settings", "Settings", "gear"]] },
  ];
  const activeTop = route.name === "finding" ? "findings" : route.name === "image" ? "images" : route.name;
  return (
    <nav className="sidebar">
      <div className="side-brand" onClick={() => go("overview")}>
        <BrandIcon size={32} />
        <div className="side-word"><b>javv</b><span>by Danube Labs</span></div>
      </div>
      <div className="side-nav">
        {groups.map((g) => (
          <div className="side-group" key={g.label}>
            <div className="side-group-label">{g.label}</div>
            {g.items.map(([key, label, icon]) => (
              <button key={key} className={"side-item " + (activeTop === key ? "side-on" : "")} onClick={() => go(key)}>
                <Icon name={icon} size={17} /><span>{label}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="side-foot">
        <div className="sweep">
          <span className="sweep-dot" />
          <div><b>Daily sweep healthy</b><span title="Jun 12, 07:00">last run 5h ago · next in 19h</span></div>
        </div>
        <div className="side-version">v1 · schema 3 · MVP</div>
      </div>
    </nav>
  );
}

function ClusterSwitcher({ cluster, setCluster }) {
  const [open, setOpen] = useState(false);
  const sel = cluster;
  const setSel = setCluster;
  return (
    <div className="dropdown cluster-dd" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button className="cluster-btn" onClick={() => setOpen((o) => !o)}>
        <span className="cluster-glyph">{sel.name[0].toUpperCase()}</span>
        <div className="cluster-info"><span className="cluster-name">{sel.name}</span><span className="cluster-id mono-cell">{sel.id}</span></div>
        <Icon name="chevron" size={14} />
      </button>
      {open && (
        <div className="dd-menu cluster-menu">
          <div className="dd-head">Clusters · by cluster_id</div>
          {JAVV.clusters.map((c) => (
            <button key={c.id} className={"dd-item " + (c.id === sel.id ? "dd-item-on" : "")} onClick={() => { setSel(c); setOpen(false); }}>
              <span className="cluster-glyph sm">{c.name[0].toUpperCase()}</span>
              <div className="cluster-info"><span className="cluster-name">{c.name}</span><span className="cluster-id mono-cell">{c.id}</span></div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function GlobalSearch({ go }) {
  const [q, setQ] = useState("");
  const wrap = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setQ(""); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const ql = q.toLowerCase();
  const res = q.length >= 2 ? {
    findings: JAVV.findings.filter((f) => f.cve.toLowerCase().includes(ql)).slice(0, 4),
    images: JAVV.images.filter((i) => (i.name + ":" + i.tag).toLowerCase().includes(ql)).slice(0, 3),
    pkgs: [...new Set(JAVV.findings.filter((f) => f.pkg.includes(ql)).map((f) => f.pkg))].slice(0, 3),
  } : null;
  const none = res && !res.findings.length && !res.images.length && !res.pkgs.length;
  const pick = (fn) => { fn(); setQ(""); };
  return (
    <div className="global-search dropdown" ref={wrap} onKeyDown={(e) => e.key === "Escape" && setQ("")}>
      <Icon name="search" size={14} />
      <input placeholder="Search CVE, image, package…" value={q} onChange={(e) => setQ(e.target.value)} />
      {res && (
        <div className="dd-menu search-menu">
          {res.findings.length > 0 && <div className="dd-head">Findings</div>}
          {res.findings.map((f) => (
            <button key={f.id} className="dd-item search-item" onClick={() => pick(() => go("finding", f))}>
              <span className="mono-cell sm strong">{f.cve}</span><Sev level={f.severity} dot={false} /><span className="search-sub mono-cell">{f.pkg}</span>
            </button>
          ))}
          {res.images.length > 0 && <div className="dd-head">Images</div>}
          {res.images.map((im) => (
            <button key={im.name + im.tag} className="dd-item search-item" onClick={() => pick(() => go("image", im))}>
              <Icon name="cube" size={13} /><span className="mono-cell sm strong">{im.name}:{im.tag}</span><span className="search-sub mono-cell">{im.ns}</span>
            </button>
          ))}
          {res.pkgs.length > 0 && <div className="dd-head">Packages</div>}
          {res.pkgs.map((p) => (
            <button key={p} className="dd-item search-item" onClick={() => pick(() => go("findings", { q: p }))}>
              <Icon name="layers" size={13} /><span className="mono-cell sm strong">{p}</span><span className="search-sub">all findings</span>
            </button>
          ))}
          {none && <div className="search-none">No matches for “{q}”</div>}
        </div>
      )}
    </div>
  );
}

function Bell({ go }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const n = JAVV.notifications;
  return (
    <div className="dropdown" ref={wrap} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button className="icon-btn" onClick={() => setOpen((o) => !o)} aria-label="notifications">
        <Icon name="bell" size={17} />{n.length > 0 && <span className="badge-num">{n.length}</span>}
      </button>
      {open && (
        <div className="dd-menu notif-menu">
          <div className="dd-head">Notifications · for you</div>
          {n.map((x, i) => (
            <button key={i} className="dd-item notif-item" onClick={() => { setOpen(false); go("finding", { cve: x.cve, severity: x.sev }); }}>
              <span className={"notif-icon " + (x.type === "sla" ? "notif-sla" : "notif-asgn")}>
                <Icon name={x.type === "sla" ? "alert" : "shield"} size={13} />
              </span>
              <span className="notif-body">
                <span className="notif-line"><b className="mono-cell">{x.cve}</b><Sev level={x.sev} dot={false} /></span>
                <span className="notif-msg">{x.msg}</span>
              </span>
              <RelTime rel={x.rel} abs={x.abs} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* Kibana-style time range picker: quick presets, relative, absolute */
function TimePicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const label = value.label;
  const [relN, setRelN] = useState(12);
  const [relUnit, setRelUnit] = useState("hours");
  const [fromD, setFromD] = useState("2026-05-14");
  const [toD, setToD] = useState("2026-06-12");
  const wrap = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const apply = (l, days) => { onChange({ label: l, days, atT: value.atT, atTLabel: value.atTLabel }); setOpen(false); };
  const rewind = (label, atTLabel) => { onChange({ ...value, atT: label !== "now", atTLabel }); setOpen(false); };
  const backToNow = () => { onChange({ ...value, atT: false, atTLabel: null }); setOpen(false); };
  const fmtD = (iso) => {
    const [y, m, d] = iso.split("-");
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m - 1] + " " + (+d) + ", " + y;
  };
  const relDays = (n, u) => ({ minutes: n / 1440, hours: n / 24, days: n, weeks: n * 7 }[u]);
  const presets = [["Today", 1], ["Last 15 minutes", 15 / 1440], ["Last 1 hour", 1 / 24], ["Last 24 hours", 1], ["Last 7 days", 7], ["Last 30 days", 30], ["Last 90 days", 90], ["Last 1 year", 365]];
  const absDays = () => Math.max(1, Math.round((new Date(toD) - new Date(fromD)) / 86400000) || 1);
  return (
    <div className="dropdown" ref={wrap} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button className={"time-range " + (value.atT ? "time-range-hist" : "")} onClick={() => setOpen((o) => !o)}>
        <Icon name={value.atT ? "rewind" : "calendar"} size={14} />{value.atT ? value.atTLabel : label}<Icon name="chevron" size={13} />
      </button>
      {open && (
        <div className="dd-menu time-menu">
          <div className="dd-head">Time-travel · rewind the whole app</div>
          <div className="time-travel">
            {[["Now", "now"], ["1 hour ago", "Jun 12, 11:04"], ["24 hours ago", "Jun 11, 12:04"], ["7 days ago", "Jun 5, 12:04"], ["30 days ago", "May 13, 12:04"]].map(([l, t]) => (
              <button key={l} className={"tt-opt " + ((l === "Now" && !value.atT) || value.atTLabel === t ? "tt-on" : "")}
                onClick={() => l === "Now" ? backToNow() : rewind(l, t)}>{l}</button>
            ))}
          </div>
          <div className="time-abs" style={{ marginTop: 2 }}>
            <input className="text-input mono-cell" type="date" value={fromD} onChange={(e) => setFromD(e.target.value)} />
            <button className="btn btn-mini time-apply" onClick={() => rewind(fmtD(fromD), "as scanned " + fmtD(fromD))}>Jump to date</button>
          </div>
          <div className="tt-note">At a past moment every screen shows <b>as-scanned</b> state - reach is bounded by each cluster's retained data.</div>
          <div className="dd-head">Trend window (dashboards)</div>
          <div className="time-rel">
            <span className="time-rel-label">Last</span>
            <input className="num-input mono-cell" type="number" min="1" value={relN} onChange={(e) => setRelN(+e.target.value)} style={{ width: 64 }} />
            <select className="select-input" style={{ minWidth: 0, width: 96 }} value={relUnit} onChange={(e) => setRelUnit(e.target.value)}>
              {["minutes", "hours", "days", "weeks"].map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
            <button className="btn btn-mini time-apply" onClick={() => apply(`Last ${relN} ${relN === 1 ? relUnit.slice(0, -1) : relUnit}`, relDays(relN, relUnit))}>Apply</button>
          </div>
          <div className="dd-head">Commonly used</div>
          <div className="time-presets">
            {presets.map(([p, days]) => (
              <button key={p} className={"time-preset " + (label === p ? "time-preset-on" : "")} onClick={() => apply(p, days)}>{p}</button>
            ))}
          </div>
          <div className="dd-head">Absolute range</div>
          <div className="time-abs">
            <input className="text-input mono-cell" type="date" value={fromD} onChange={(e) => setFromD(e.target.value)} />
            <span className="time-arrow">→</span>
            <input className="text-input mono-cell" type="date" value={toD} onChange={(e) => setToD(e.target.value)} />
            <button className="btn btn-mini time-apply" onClick={() => apply(fromD === toD ? fmtD(fromD) : fmtD(fromD) + " → " + fmtD(toD), absDays())}>Apply</button>
          </div>
          <div className="time-note">Drives the OpenSearch query window - all counts and charts follow it.</div>
        </div>
      )}
    </div>
  );
}

function Topbar({ go, cluster, setCluster, timeRange, setTimeRange }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const wrap = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setMenuOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  return (
    <header className="topbar">
      <ClusterSwitcher cluster={cluster} setCluster={setCluster} />
      <div className="topbar-mid">
        <TimePicker value={timeRange} onChange={setTimeRange} />
        <GlobalSearch go={go} />
      </div>
      <div className="topbar-right">
        <Bell go={go} />
        <div className="dropdown" ref={wrap}>
          <button className="avatar" title="Lorem Ipsum" onClick={() => setMenuOpen((o) => !o)}>LI</button>
          {menuOpen && (
            <div className="dd-menu user-menu">
              <div className="user-menu-head">
                <Avatar initials="LI" tone="#C0271D" size={34} />
                <div><b>Lorem Ipsum</b><span className="user-role">Security Lead</span></div>
              </div>
              <button className="dd-item" onClick={() => { setMenuOpen(false); go("settings"); }}><Icon name="gear" size={14} />Settings</button>
              <button className="dd-item" onClick={() => { setMenuOpen(false); go("login"); }}><Icon name="arrowback" size={14} />Sign out</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function Login({ go }) {
  const [stage, setStage] = useState("signin"); // signin | bootstrap
  if (stage === "bootstrap") {
    return (
      <div className="login-stage">
        <div className="login-card">
          <div className="login-brand"><BrandIcon size={44} /><div className="side-word"><b>javv</b><span>by Danube Labs</span></div></div>
          <div className="boot-banner"><Icon name="key" size={14} />First sign-in for the bootstrap admin - set a new password to continue.</div>
          <label className="fld-label">New password</label>
          <input className="fld" type="password" placeholder="••••••••••••" />
          <label className="fld-label">Confirm password</label>
          <input className="fld" type="password" placeholder="••••••••••••" />
          <p className="login-note">Minimum 12 characters. The seeded password is invalidated once you set your own.</p>
          <button className="btn btn-primary btn-block" onClick={() => go("allclusters")}>Set password &amp; continue</button>
        </div>
      </div>
    );
  }
  return (
    <div className="login-stage">
      <div className="login-card">
        <div className="login-brand"><BrandIcon size={44} /><div className="side-word"><b>javv</b><span>by Danube Labs</span></div></div>
        <p className="login-sub">just another vulnerability viewer</p>
        <label className="fld-label">Username</label>
        <input className="fld" type="text" placeholder="username" defaultValue="lorem.ipsum" />
        <label className="fld-label">Password</label>
        <input className="fld" type="password" placeholder="••••••••••••" />
        <button className="btn btn-primary btn-block" onClick={() => go("allclusters")}>Sign in</button>
        <p className="login-note">Local account · one session per browser, shared across tabs. What you can do is governed by your <b>capabilities</b>, not just a role name. <button className="link-btn" onClick={() => setStage("bootstrap")}>First-run admin?</button></p>
      </div>
    </div>
  );
}

function App() {
  const [route, setRoute] = useState({ name: "allclusters", data: null });
  const [cluster, setCluster] = useState(JAVV.clusters.find((c) => c.current));
  const [timeRange, setTimeRange] = useState({ label: "Last 30 days", days: 30 });
  const go = (name, data = null) => { setRoute({ name, data }); window.scrollTo(0, 0); const c = document.querySelector(".content"); if (c) c.scrollTop = 0; };

  if (route.name === "login") return <Login go={go} />;

  const firstRun = cluster && cluster.firstRun;
  let view;
  switch (route.name) {
    case "overview": view = firstRun ? <FirstRun go={go} clusterName={cluster.name} what="scan results" /> : <Overview go={go} cluster={cluster} />; break;
    case "findings": view = firstRun ? <FirstRun go={go} clusterName={cluster.name} what="findings" /> : <Findings key={JSON.stringify(route.data)} go={go} preset={route.data} cluster={cluster} />; break;
    case "finding": view = <FindingDetail go={go} finding={route.data} />; break;
    case "images": view = firstRun ? <FirstRun go={go} clusterName={cluster.name} what="images" /> : <Images go={go} cluster={cluster} atT={timeRange.atT} atTLabel={timeRange.atTLabel} />; break;
    case "image": view = <ImageDetail go={go} image={route.data} atT={timeRange.atT} atTLabel={timeRange.atTLabel} />; break;
    case "approvals": view = <Approvals go={go} />; break;
    case "audit": view = <AuditLog go={go} />; break;
    case "heroes": view = <Heroes go={go} timeRange={timeRange} />; break;
    case "views": view = <SavedViews go={go} />; break;
    case "scanstatus": view = <ScannerStatus go={go} />; break;
    case "settings": view = <Settings go={go} />; break;
    default: view = <AllClusters go={go} setCluster={setCluster} />;
  }

  return (
    <div className="app">
      <Sidebar route={route} go={go} />
      <main className="main">
        <Topbar go={go} cluster={cluster} setCluster={setCluster} timeRange={timeRange} setTimeRange={setTimeRange} />
        {timeRange.atT && <HistoryBanner atTLabel={timeRange.atTLabel} onBack={() => setTimeRange({ ...timeRange, atT: false, atTLabel: null })} />}
        <div className="content">{view}</div>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
