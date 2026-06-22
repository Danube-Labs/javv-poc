/* JAVV - shared filtering module.
   One FIELDS config per screen drives BOTH the facet rail and the filter bar.
   Exports: useFilters (state), FacetGroup, FacetRail, FilterBar, ColumnsMenu. */

function useFilters(fields, preset) {
  const empty = () => Object.fromEntries(fields.map((f) => [f.key, new Set()]));
  const [sel, setSel] = useState(() => {
    const s = empty();
    if (preset && preset.filters) for (const k in preset.filters) (preset.filters[k] || []).forEach((v) => s[k] && s[k].add(v));
    return s;
  });
  const toggle = (field, val) => setSel((prev) => {
    const next = { ...prev, [field]: new Set(prev[field]) };
    next[field].has(val) ? next[field].delete(val) : next[field].add(val);
    return next;
  });
  const clearField = (field) => setSel((prev) => ({ ...prev, [field]: new Set() }));
  const clearAll = () => setSel(empty());
  const hasFilters = fields.some((f) => sel[f.key].size > 0);
  return { sel, toggle, clearField, clearAll, hasFilters };
}

function FacetGroup({ title, items, sel, onToggle, render }) {
  return (
    <div className="facet">
      <div className="facet-title">{title}</div>
      {items.map((it) => (
        <button key={it.key} className={"facet-row " + (sel.has(it.key) ? "facet-on" : "")} onClick={() => onToggle(it.key)}>
          <span className="facet-check" />
          <span className="facet-label">{render ? render(it.key) : it.key}</span>
          <span className="facet-count">{fmt(it.count)}</span>
        </button>
      ))}
    </div>
  );
}

/* Renders the full left rail from the same FIELDS config the FilterBar uses. */
function FacetRail({ fields, sel, toggle, countVal, header }) {
  return (
    <aside className="facets">
      {header}
      {fields.map((f) => (
        <FacetGroup key={f.key} title={f.label} sel={sel[f.key]} onToggle={(v) => toggle(f.key, v)}
          items={f.values.map((v) => ({ key: v, count: countVal(f.key, v) }))}
          render={(v) => f.render(v)} />
      ))}
    </aside>
  );
}

/* Kibana-style filter bar (keyboard: Esc closes, arrows navigate). */
function FilterBar({ fields, sel, toggle, clearField, clearAll, countVal, extra }) {
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [vq, setVq] = useState("");
  const wrap = useRef(null);

  useEffect(() => {
    const onDoc = (e) => { if (wrap.current && !wrap.current.contains(e.target)) { setOpen(false); setEdit(null); } };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const onKey = (e) => {
    if (e.key === "Escape") { setOpen(false); setEdit(null); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const menu = wrap.current && wrap.current.querySelector(".dd-menu");
      if (!menu) return;
      e.preventDefault();
      const items = [...menu.querySelectorAll("button")];
      const idx = items.indexOf(document.activeElement);
      const next = e.key === "ArrowDown" ? Math.min(idx + 1, items.length - 1) : Math.max(idx - 1, 0);
      if (items[next]) items[next].focus();
    }
  };

  const openPicker = () => { setEdit(null); setVq(""); setOpen(true); };
  const openField = (k) => { setEdit(k); setVq(""); setOpen(true); };
  const active = fields.filter((f) => sel[f.key].size > 0);
  const field = edit ? fields.find((f) => f.key === edit) : null;
  const pillText = (f) => {
    const vals = [...sel[f.key]].map(f.valLabel);
    return vals.length <= 2 ? vals.join(", ") : `${vals.slice(0, 2).join(", ")} +${vals.length - 2}`;
  };

  return (
    <div className="filter-bar" ref={wrap} onKeyDown={onKey}>
      {active.map((f) => (
        <button key={f.key} className="fpill" onClick={() => openField(f.key)}>
          <span className="fpill-field">{f.label}</span>
          <span className="fpill-op">{sel[f.key].size > 1 ? "is one of" : "is"}</span>
          <span className="fpill-vals">{pillText(f)}</span>
          <span className="fpill-x" onClick={(e) => { e.stopPropagation(); clearField(f.key); }}>×</span>
        </button>
      ))}
      <div className="dropdown">
        <button className="add-filter" onClick={() => (open ? (setOpen(false), setEdit(null)) : openPicker())}>
          <Icon name="plus" size={13} />Add filter
        </button>
        {open && (
          <div className="dd-menu filter-menu">
            {!field && (
              <>
                <div className="dd-head">Filter by field</div>
                {fields.map((f) => (
                  <button key={f.key} className="dd-item filter-field" onClick={() => openField(f.key)}>
                    <span>{f.label}</span>
                    {sel[f.key].size > 0 && <span className="field-badge">{sel[f.key].size}</span>}
                    <Icon name="chevron" size={13} />
                  </button>
                ))}
              </>
            )}
            {field && (
              <>
                <button className="filter-back" onClick={() => setEdit(null)}><Icon name="arrowback" size={13} />{field.label}</button>
                {field.values.length > 8 && (
                  <div className="filter-vsearch"><Icon name="search" size={13} /><input autoFocus placeholder="Filter values…" value={vq} onChange={(e) => setVq(e.target.value)} /></div>
                )}
                <div className="filter-values">
                  {field.values.filter((v) => !vq || field.valLabel(v).toLowerCase().includes(vq.toLowerCase())).map((v) => (
                    <button key={v} className={"facet-row " + (sel[field.key].has(v) ? "facet-on" : "")} onClick={() => toggle(field.key, v)}>
                      <span className="facet-check" />
                      <span className="facet-label">{field.render(v)}</span>
                      <span className="facet-count">{fmt(countVal(field.key, v))}</span>
                    </button>
                  ))}
                </div>
                {sel[field.key].size > 0 && <button className="filter-clear-field" onClick={() => clearField(field.key)}>Clear {field.label.toLowerCase()}</button>}
              </>
            )}
          </div>
        )}
      </div>
      {active.length > 0 && <button className="clear-all" onClick={clearAll}>Clear all</button>}
      {extra}
    </div>
  );
}

/* Column visibility + density menu. */
function ColumnsMenu({ cols, hidden, toggleCol, dense, setDense }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  return (
    <div className="dropdown cols-dd" ref={wrap} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button className="btn btn-mini" onClick={() => setOpen(!open)}><Icon name="columns" size={13} />Columns</button>
      {open && (
        <div className="dd-menu filter-menu cols-menu">
          <div className="dd-head">Density</div>
          <div className="seg" style={{ margin: "2px 8px 8px" }}>
            <button className={"seg-opt " + (dense ? "seg-on" : "")} onClick={() => setDense(true)}>Compact</button>
            <button className={"seg-opt " + (!dense ? "seg-on" : "")} onClick={() => setDense(false)}>Comfortable</button>
          </div>
          <div className="dd-head">Columns</div>
          {cols.map(([k, label]) => (
            <button key={k} className={"facet-row " + (!hidden.has(k) ? "facet-on" : "")} onClick={() => toggleCol(k)}>
              <span className="facet-check" /><span className="facet-label">{label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

Object.assign(window, { useFilters, FacetGroup, FacetRail, FilterBar, ColumnsMenu });
