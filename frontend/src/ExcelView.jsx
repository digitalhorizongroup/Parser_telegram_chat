import { useEffect, useMemo, useState } from "react";
import { Activity, Download, Filter, Group, Layers3, Search, Settings2, SortAsc } from "lucide-react";
import { api } from "./api";
import "./excel-view.css";

const OPERATORS = [
  ["contains", "содержит"], ["eq", "="], ["neq", "≠"], ["gt", ">"],
  ["gte", "≥"], ["lt", "<"], ["lte", "≤"], ["empty", "пусто"],
];
const loadSettings = () => {
  try { return JSON.parse(localStorage.getItem("telescope-grid-settings")) || {}; } catch { return {}; }
};
const saveSettings = (value) => localStorage.setItem("telescope-grid-settings", JSON.stringify(value));
const display = (value) => value === null || value === undefined || value === "" ? "—" : typeof value === "boolean" ? (value ? "Да" : "Нет") : String(value);
function calculate(row, formula) {
  const match = formula.trim().match(/^=?\s*([\w]+)\s*([+\-*/])\s*([\w.]+)\s*$/);
  if (!match) return "#FORMULA";
  const left = Number(row[match[1]] ?? 0), right = Number(row[match[3]] ?? match[3]);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return "#VALUE";
  return ({ "+": left + right, "-": left - right, "*": left * right, "/": right ? left / right : 0 })[match[2]];
}

export default function ExcelView({ runs, initialRun }) {
  const stored = loadSettings();
  const [data, setData] = useState({ rows: [], columns: [], total: 0, summary: {}, groups: [], duplicates: [] });
  const [runId, setRunId] = useState(initialRun || ""), [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0), [limit, setLimit] = useState(100);
  const [filters, setFilters] = useState([]), [sorts, setSorts] = useState([]);
  const [groupBy, setGroupBy] = useState(""), [duplicateField, setDuplicateField] = useState("");
  const [panel, setPanel] = useState(""), [loading, setLoading] = useState(false), [error, setError] = useState("");
  const [selected, setSelected] = useState(new Set()), [activeCell, setActiveCell] = useState("");
  const [settings, setSettings] = useState({ hidden: stored.hidden || [], widths: stored.widths || {}, order: stored.order || [], pinned: stored.pinned || "title", formulas: stored.formulas || [] });
  const updateSettings = (next) => { setSettings(next); saveSettings(next); };
  const params = useMemo(() => {
    const value = new URLSearchParams({ limit, offset, q: query, filters: JSON.stringify(filters), sorts: JSON.stringify(sorts) });
    if (runId) value.set("run_id", runId);
    if (groupBy) value.set("group_by", groupBy);
    if (duplicateField) value.set("duplicates", duplicateField);
    return value;
  }, [runId, query, filters, sorts, offset, limit, groupBy, duplicateField]);
  useEffect(() => {
    const timer = setTimeout(async () => {
      setLoading(true); setError("");
      try { const value = await api(`/api/results/grid?${params}`); setData(value); if (!runId && value.run_id) setRunId(String(value.run_id)); }
      catch (x) { setError(x.message); } finally { setLoading(false); }
    }, 180);
    return () => clearTimeout(timer);
  }, [params]);
  useEffect(() => setOffset(0), [runId, query, filters, sorts, limit, groupBy, duplicateField]);

  const sourceColumns = data.columns || [], byKey = Object.fromEntries(sourceColumns.map((x) => [x.key, x]));
  const ordered = [...new Set([...(settings.order || []), ...sourceColumns.map((x) => x.key)])]
    .filter((key) => byKey[key] && !settings.hidden.includes(key)).map((key) => byKey[key]);
  const formulaColumns = settings.formulas.map((item) => ({ ...item, key: `formula:${item.name}`, label: item.name, type: "number", formula: true }));
  const columns = [...ordered, ...formulaColumns];
  const selectedRows = data.rows.filter((row) => selected.has(row.chat_id));
  const exportParams = new URLSearchParams(params); exportParams.delete("limit"); exportParams.delete("offset");
  if (selected.size) exportParams.set("ids", [...selected].join(","));
  const togglePanel = (name) => setPanel(panel === name ? "" : name);
  const toggleRow = (id) => setSelected((old) => { const next = new Set(old); next.has(id) ? next.delete(id) : next.add(id); return next; });
  async function copySelection() {
    const rows = selectedRows.length ? selectedRows : data.rows;
    const text = [columns.map((x) => x.label).join("\t"), ...rows.map((row) => columns.map((col) => display(col.formula ? calculate(row, col.expression) : row[col.key])).join("\t"))].join("\n");
    await navigator.clipboard.writeText(text);
  }
  function addFormula() {
    const name = prompt("Название вычисляемого столбца:", "Индекс"); if (!name) return;
    const expression = prompt("Формула, например messages_24h / participants:", "messages_24h / participants"); if (!expression) return;
    updateSettings({ ...settings, formulas: [...settings.formulas, { name, expression }] });
  }
  function moveColumn(key, delta) {
    const list = ordered.map((x) => x.key), index = list.indexOf(key), target = index + delta;
    if (target < 0 || target >= list.length) return;
    [list[index], list[target]] = [list[target], list[index]]; updateSettings({ ...settings, order: list });
  }
  return <div className="excel-shell">
    <div className="excel-toolbar">
      <label className="excel-search"><Search size={15}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по всем данным"/></label>
      <select value={runId} onChange={(e) => setRunId(e.target.value)}>{runs.map((r) => <option value={r.id} key={r.id}>Запуск #{r.id}</option>)}</select>
      <button onClick={() => togglePanel("filter")} className={filters.length ? "active" : ""}><Filter size={15}/>Фильтры {filters.length || ""}</button>
      <button onClick={() => togglePanel("sort")} className={sorts.length ? "active" : ""}><SortAsc size={15}/>Сортировка</button>
      <button onClick={() => togglePanel("columns")}><Settings2 size={15}/>Столбцы</button>
      <button onClick={addFormula}><Activity size={15}/>Формула</button>
      <button onClick={() => togglePanel("group")}><Group size={15}/>Группа</button>
      <button onClick={() => togglePanel("stats")}><Layers3 size={15}/>Статистика</button>
      <button onClick={() => togglePanel("export")}><Download size={15}/>Экспорт</button>
    </div>
    {panel === "filter" && <div className="excel-panel"><b>Фильтры</b>{filters.map((f,i) => <div className="rule" key={i}><select value={f.field} onChange={(e) => setFilters(filters.map((x,j) => j===i?{...x,field:e.target.value}:x))}>{sourceColumns.map((c)=><option value={c.key} key={c.key}>{c.label}</option>)}</select><select value={f.op} onChange={(e) => setFilters(filters.map((x,j)=>j===i?{...x,op:e.target.value}:x))}>{OPERATORS.map(([v,l])=><option value={v} key={v}>{l}</option>)}</select><input value={f.value} onChange={(e)=>setFilters(filters.map((x,j)=>j===i?{...x,value:e.target.value}:x))}/><button onClick={()=>setFilters(filters.filter((_,j)=>j!==i))}>×</button></div>)}<button onClick={()=>setFilters([...filters,{field:sourceColumns[0]?.key||"title",op:"contains",value:""}])}>+ Добавить фильтр</button></div>}
    {panel === "sort" && <div className="excel-panel"><b>Многоуровневая сортировка</b>{sorts.map((s,i)=><div className="rule" key={i}><select value={s.field} onChange={(e)=>setSorts(sorts.map((x,j)=>j===i?{...x,field:e.target.value}:x))}>{sourceColumns.map((c)=><option value={c.key} key={c.key}>{c.label}</option>)}</select><select value={s.dir} onChange={(e)=>setSorts(sorts.map((x,j)=>j===i?{...x,dir:e.target.value}:x))}><option value="asc">По возрастанию</option><option value="desc">По убыванию</option></select><button onClick={()=>setSorts(sorts.filter((_,j)=>j!==i))}>×</button></div>)}<button onClick={()=>setSorts([...sorts,{field:"score",dir:"desc"}])}>+ Добавить уровень</button></div>}
    {panel === "columns" && <div className="excel-panel columns-panel"><b>Столбцы и закрепление</b>{sourceColumns.map((c)=><div key={c.key}><label><input type="checkbox" checked={!settings.hidden.includes(c.key)} onChange={()=>updateSettings({...settings,hidden:settings.hidden.includes(c.key)?settings.hidden.filter(x=>x!==c.key):[...settings.hidden,c.key]})}/>{c.label}</label><input type="range" min="80" max="320" value={settings.widths[c.key]||140} onChange={(e)=>updateSettings({...settings,widths:{...settings.widths,[c.key]:Number(e.target.value)}})}/><button onClick={()=>moveColumn(c.key,-1)}>←</button><button onClick={()=>moveColumn(c.key,1)}>→</button><button className={settings.pinned===c.key?"active":""} onClick={()=>updateSettings({...settings,pinned:settings.pinned===c.key?"":c.key})}>Закрепить</button></div>)}</div>}
    {panel === "group" && <div className="excel-panel"><b>Группировка и дубликаты</b><div className="rule"><select value={groupBy} onChange={(e)=>setGroupBy(e.target.value)}><option value="">Без группировки</option>{sourceColumns.map(c=><option key={c.key} value={c.key}>{c.label}</option>)}</select><select value={duplicateField} onChange={(e)=>setDuplicateField(e.target.value)}><option value="">Не искать дубликаты</option>{sourceColumns.map(c=><option key={c.key} value={c.key}>Дубликаты: {c.label}</option>)}</select></div>{data.groups?.length>0&&<div className="chips">{data.groups.map((x,i)=><span key={i}>{display(x.value)} <b>{x.count}</b></span>)}</div>}{data.duplicates?.length>0&&<div className="chips danger-chips">{data.duplicates.map((x,i)=><span key={i}>{display(x.value)} <b>{x.count}</b></span>)}</div>}</div>}
    {panel === "stats" && <div className="excel-panel stats-panel"><b>Статистика по всей отфильтрованной выборке</b>{sourceColumns.filter((c)=>c.type==="number"&&data.summary?.[c.key]?.sum!=null).map((c)=><span key={c.key}><small>{c.label}</small><b>Σ {Number(data.summary[c.key].sum).toLocaleString("ru-RU")}</b><em>ср. {Number(data.summary[c.key].avg).toLocaleString("ru-RU",{maximumFractionDigits:2})}</em></span>)}</div>}
    {panel === "export" && <div className="excel-panel export-panel"><b>Экспорт: {selected.size ? `выбрано ${selected.size}` : `отфильтровано ${data.total}`}</b><a href={`/download/results.xlsx?${exportParams}`}><Download size={15}/>Excel .xlsx</a><a href={`/download/results.csv?${exportParams}`}><Download size={15}/>CSV</a><button onClick={copySelection}>Скопировать TSV</button></div>}
    {error && <div className="notice error">{error}</div>}
    <div className="excel-meta"><span><i className={loading?"loading":""}/>{loading?"Обновление…":`Записей: ${data.total}`}</span><span>Выбрано: {selected.size}</span><span>Источник: SQLite · read-only</span></div>
    <div className="excel-grid-wrap"><table className="excel-grid"><thead><tr><th className="row-number"><input type="checkbox" checked={data.rows.length>0&&data.rows.every(r=>selected.has(r.chat_id))} onChange={()=>setSelected(data.rows.every(r=>selected.has(r.chat_id))?new Set():new Set(data.rows.map(r=>r.chat_id)))}/></th>{columns.map((c)=><th key={c.key} className={settings.pinned===c.key?"pinned":""} style={{width:settings.widths[c.key]||140,minWidth:settings.widths[c.key]||140}}>{c.label}{c.formula&&<button onClick={()=>updateSettings({...settings,formulas:settings.formulas.filter(x=>x.name!==c.name)})}>×</button>}</th>)}</tr></thead><tbody>{data.rows.map((row,index)=><tr key={row.chat_id} className={selected.has(row.chat_id)?"selected":""}><td className="row-number"><span>{offset+index+1}</span><input type="checkbox" checked={selected.has(row.chat_id)} onChange={()=>toggleRow(row.chat_id)}/></td>{columns.map((c)=>{const key=`${row.chat_id}:${c.key}`,value=c.formula?calculate(row,c.expression):row[c.key];return <td key={c.key} className={`${activeCell===key?"active-cell":""} ${settings.pinned===c.key?"pinned":""} ${c.type==="number"&&Number(value)>0?"numeric-hot":""}`} onClick={()=>setActiveCell(key)} title={display(value)}>{c.key==="username"&&value?<a href={`https://t.me/${value}`} target="_blank">@{value}</a>:display(value)}</td>})}</tr>)}</tbody></table></div>
    <div className="excel-footer"><div><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-limit))}>←</button><span>{data.total?`${offset+1}–${Math.min(offset+limit,data.total)} из ${data.total}`:"0 записей"}</span><button disabled={offset+limit>=data.total} onClick={()=>setOffset(offset+limit)}>→</button><select value={limit} onChange={(e)=>setLimit(Number(e.target.value))}><option>50</option><option>100</option><option>250</option><option>500</option></select></div><div className="quick-stats"><Layers3 size={14}/>{activeCell?`Ячейка ${activeCell.split(":")[1]}`:"Выберите ячейку"}</div></div>
  </div>;
}
