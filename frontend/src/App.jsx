import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Database,
  Download,
  FileText,
  History,
  LogOut,
  Moon,
  Pause,
  Play,
  Radio,
  ScrollText,
  ShieldCheck,
  Trash2,
  Users,
  Wifi,
} from "lucide-react";
import { api, setCsrf } from "./api";
import ExcelView from "./ExcelView";
import "./management.css";
import "./phone-auth.css";
import "./results.css";
import "./live-results.css";

const initial = {
  status: "idle",
  total: 0,
  completed: 0,
  sessions: 0,
  running: false,
  report: false,
  database: false,
};
const fmtDate = (value) =>
  value ? new Date(value).toLocaleString("ru-RU") : "—";
const fmtSize = (value) =>
  value < 1024 ? `${value} Б` : `${(value / 1024).toFixed(1)} КБ`;
const fmtDuration = (seconds) => {
  const value = Math.max(0, Number(seconds) || 0);
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return [days && `${days} д.`, hours && `${hours} ч.`, `${minutes} мин.`]
    .filter(Boolean).join(" ");
};
function Login({ onLogin }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      const data = await api("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: f.get("username"),
          password: f.get("password"),
        }),
      });
      setCsrf(data.csrf);
      onLogin(data);
    } catch (x) {
      setError(x.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <div className="glow one" />
      <div className="glow two" />
      <form className="login-card" onSubmit={submit}>
        <Logo />
        <span className="kicker">TELEGRAM INTELLIGENCE</span>
        <h1>Возвращайтесь к данным</h1>
        <p>Войдите в защищённый центр управления.</p>
        {error && <div className="notice error">{error}</div>}
        <label>
          Логин
          <input name="username" autoComplete="username" required autoFocus />
        </label>
        <label>
          Пароль
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        <button disabled={busy}>
          {busy ? "Проверка…" : "Войти"}
          <ArrowRight size={18} />
        </button>
      </form>
    </main>
  );
}
function Logo() {
  return (
    <div className="logo">
      <span>
        <Radio size={19} />
      </span>
      TeleScope
    </div>
  );
}
function Drop({
  name,
  multiple,
  accept,
  icon: Icon,
  title,
  subtitle,
  onChange,
}) {
  return (
    <label className="drop">
      <input
        type="file"
        name={name}
        multiple={multiple}
        accept={accept}
        onChange={onChange}
      />
      <Icon size={27} />
      <b>{title}</b>
      <small>{subtitle}</small>
    </label>
  );
}
function PhoneAuth({ onDone, onMessage }) {
  const [phone, setPhone] = useState(""),
    [code, setCode] = useState(""),
    [password, setPassword] = useState(""),
    [token, setToken] = useState(""),
    [needsPassword, setNeedsPassword] = useState(false),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState("");
  function reset() {
    setPhone("");
    setCode("");
    setPassword("");
    setToken("");
    setNeedsPassword(false);
    setStatus("");
  }
  async function send() {
    setBusy(true);
    setStatus("Отправляем запрос в Telegram…");
    try {
      const r = await api("/api/accounts/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      setToken(r.token);
      setStatus("Код отправлен. Проверьте сообщения от Telegram.");
    } catch (x) {
      setStatus(x.message);
      onMessage({ type: "error", text: x.message });
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    setBusy(true);
    setStatus("Проверяем код…");
    try {
      const r = await api("/api/accounts/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, code, password }),
      });
      if (r.requires_password) {
        setNeedsPassword(true);
        setStatus(r.message);
      } else {
        onMessage({
          type: "ok",
          text: `Аккаунт ${r.account?.name || ""} авторизован.`,
        });
        reset();
        onDone();
      }
    } catch (x) {
      setStatus(x.message);
      onMessage({ type: "error", text: x.message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="phone-auth">
      <div>
        <b>Авторизация по номеру</b>
        <small>
          Можно вводить цифрами без «+». Код обычно приходит в приложение
          Telegram.
        </small>
      </div>
      <div className="auth-fields">
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="Код страны и номер"
          disabled={!!token}
        />
        {token && (
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            placeholder="Код Telegram"
          />
        )}
        {needsPassword && (
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="Пароль 2FA"
          />
        )}
        <button
          type="button"
          onClick={token ? confirm : send}
          disabled={busy || (!token && !phone) || (token && !code)}
        >
          {busy
            ? "Подождите…"
            : token
              ? needsPassword
                ? "Подтвердить 2FA"
                : "Подтвердить код"
              : "Получить код"}
        </button>
      </div>
      {status && <div className="auth-status">{status}</div>}
      {token && (
        <button
          type="button"
          className="auth-reset"
          onClick={reset}
          disabled={busy}
        >
          Изменить номер / начать заново
        </button>
      )}
    </div>
  );
}
function ProxySettings({ values, onDone, onMessage }) {
  const [form, setForm] = useState({ type: "socks5", host: "", port: "", username: "", password: "" });
  const [busy, setBusy] = useState("");
  const change = (key) => (event) => setForm({ ...form, [key]: event.target.value });
  async function save() {
    setBusy("save");
    try {
      const result = await api("/api/proxy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      onMessage({ type: "ok", text: result.message }); setForm({ type: "socks5", host: "", port: "", username: "", password: "" }); onDone();
    } catch (error) { onMessage({ type: "error", text: error.message }); }
    finally { setBusy(""); }
  }
  async function test(id) {
    setBusy(id);
    try { const result = await api("/api/proxy/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }); onMessage({ type: "ok", text: result.message }); }
    catch (error) { onMessage({ type: "error", text: error.message }); }
    finally { setBusy(""); }
  }
  async function disable(id) {
    setBusy(`delete-${id}`);
    try { const result = await api(`/api/proxy/${encodeURIComponent(id)}`, { method: "DELETE" }); onMessage({ type: "ok", text: result.message }); onDone(); }
    catch (error) { onMessage({ type: "error", text: error.message }); }
    finally { setBusy(""); }
  }
  return <div className="proxy-card">
    <div className="proxy-heading"><span><Wifi size={18}/></span><div><b>Пул прокси</b><small>Автоматическое равномерное распределение между аккаунтами</small></div><i className={values.length ? "on" : ""}>{values.length} шт.</i></div>
    <div className="proxy-fields"><select value={form.type} onChange={change("type")}><option value="socks5">SOCKS5</option><option value="http">HTTP</option></select><input value={form.host} onChange={change("host")} placeholder="IP или домен"/><input value={form.port} onChange={change("port")} inputMode="numeric" placeholder="Порт"/><input value={form.username} onChange={change("username")} placeholder="Логин"/><input value={form.password} onChange={change("password")} type="password" placeholder="Пароль"/></div>
    <div className="proxy-actions"><button type="button" onClick={save} disabled={!!busy || !form.host || !form.port}>{busy === "save" ? "Добавляем…" : "+ Добавить прокси"}</button><small>Можно добавить один или несколько прокси.</small></div>
    <div className="proxy-list">{values.map((item, index)=><article key={item.id}><span>{index+1}</span><div><b>{item.host}:{item.port}</b><small>{item.type.toUpperCase()} · {item.username || "без авторизации"}</small></div><button className="secondary" onClick={()=>test(item.id)} disabled={!!busy}>{busy===item.id?"Проверка…":"Проверить"}</button><button className="icon-danger" onClick={()=>disable(item.id)} disabled={!!busy}><Trash2 size={15}/></button></article>)}{!values.length&&<div className="empty">Добавьте первый прокси</div>}</div>
  </div>;
}
function Dashboard({ user, onLogout }) {
  const [data, setData] = useState(initial),
    [runs, setRuns] = useState([]),
    [accounts, setAccounts] = useState([]),
    [proxies, setProxies] = useState([]),
    [logs, setLogs] = useState({ files: [], content: "", selected: "" }),
    [message, setMessage] = useState(null),
    [busy, setBusy] = useState(false),
    [keywordName, setKeywordName] = useState("");
  const form = useRef();
  async function refresh() {
    try {
      const [d, r, a, l, p] = await Promise.all([
        api("/api/dashboard"),
        api("/api/runs"),
        api("/api/accounts"),
        api("/api/logs"),
        api("/api/proxy"),
      ]);
      setData(d);
      setRuns(r.runs);
      setAccounts(a.accounts);
      setLogs(l);
      setProxies(p.proxies || []);
    } catch (e) {
      if (e.message === "authentication_required") onLogout();
    }
  }
  async function loadLog(name) {
    try {
      setLogs(await api(`/api/logs?name=${encodeURIComponent(name)}`));
    } catch (x) {
      setMessage({ type: "error", text: x.message });
    }
  }
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, []);
  const done = data.live?.completed ?? data.completed ?? 0,
    total = data.live?.total ?? data.total ?? 0,
    pct = total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const page = {
      "/": "overview",
      "/parsing": "parsing",
      "/runs": "runs",
      "/accounts": "accounts",
      "/logs": "logs",
      "/artifacts": "artifacts",
    }[location.pathname] || "overview",
    pageMeta = {
      overview: ["CONTROL CENTER", `Добро пожаловать, ${user}`, "Общее состояние парсера и Telegram-аккаунтов."],
      parsing: ["PARSING WORKSPACE", "Парсинг", "Запускайте поиск и следите за прогрессом в реальном времени."],
      runs: ["RUN HISTORY", "Запуски", "История, статусы и результаты всех сканирований."],
      accounts: ["ACCOUNT POOL", "Telegram-аккаунты", "Авторизация, загрузка и управление рабочими сессиями."],
      logs: ["LIVE OUTPUT", "Логи", "Технические события и диагностика работы парсера."],
      artifacts: ["DATA EXPORT", "Файлы и экспорт", "Таблица, Excel-отчёт, SQLite и управление данными."],
    }[page];
  async function start(e) {
    e.preventDefault();
    await launch(new FormData(e.currentTarget), false);
  }
  async function launch(body, resumed) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api("/api/start", { method: "POST", body });
      setMessage({
        type: "ok",
        text: `${resumed ? "Сканирование продолжено" : "Запуск создан"}. Новых аккаунтов: ${result.uploaded}. Лог: ${result.log}`,
      });
      refresh();
    } catch (x) {
      setMessage({ type: "error", text: x.message });
    } finally {
      setBusy(false);
    }
  }
  async function resume() {
    if (!form.current) {
      location.href = "/parsing";
      return;
    }
    await launch(new FormData(form.current), true);
  }
  async function pause() {
    if (!confirm("Поставить сканирование на паузу? Прогресс будет сохранён."))
      return;
    try {
      await api("/api/pause", { method: "POST" });
      setMessage({
        type: "ok",
        text: "Сканирование на паузе. Прогресс сохранён — можно продолжить позже.",
      });
      refresh();
    } catch (x) {
      setMessage({ type: "error", text: x.message });
    }
  }
  async function clear() {
    if (!confirm("Удалить все Telegram-сессии?")) return;
    try {
      const r = await api("/api/sessions", { method: "DELETE" });
      setMessage({ type: "ok", text: `Удалено: ${r.removed}` });
      refresh();
    } catch (x) {
      setMessage({ type: "error", text: x.message });
    }
  }
  async function removeAccount(name) {
    if (!confirm("Удалить этот аккаунт?")) return;
    try {
      await api(`/api/accounts/${encodeURIComponent(name)}`, {
        method: "DELETE",
      });
      refresh();
    } catch (x) {
      setMessage({ type: "error", text: x.message });
    }
  }
  async function assignRole(name, role) {
    try {
      await api(`/api/accounts/${encodeURIComponent(name)}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      setMessage({ type: "ok", text: "Назначение аккаунта сохранено." });
      refresh();
    } catch (x) {
      setMessage({ type: "error", text: x.message });
    }
  }
  return (
    <div className="layout">
      <aside>
        <div className="brand-block">
          <Logo />
          <small>Telegram Intelligence</small>
        </div>
        <nav>
          <a className={page === "overview" ? "active" : ""} href="/">
            <BarChart3 />
            Обзор
          </a>
          <a className={page === "parsing" ? "active" : ""} href="/parsing">
            <Play />
            Парсинг
          </a>
          <a className={page === "runs" ? "active" : ""} href="/runs">
            <History />
            Запуски
          </a>
          <a className={page === "accounts" ? "active" : ""} href="/accounts">
            <Users />
            Аккаунты
          </a>
          <a className={page === "logs" ? "active" : ""} href="/logs">
            <ScrollText />
            Логи
          </a>
          <a href="/results">
            <Activity />
            Результаты
          </a>
          <a className={page === "artifacts" ? "active" : ""} href="/artifacts">
            <Database />
            Файлы
          </a>
        </nav>
        <div className="account">
          <span>{user?.[0]?.toUpperCase()}</span>
          <div>
            <b>{user}</b>
            <small>Администратор</small>
          </div>
        </div>
        <div className="system-badge">
          <i />
          <span>
            <b>Система онлайн</b>
            <small>{data.sessions || 0} аккаунтов подключено</small>
          </span>
        </div>
        <button className="logout" onClick={onLogout}>
          <LogOut size={17} />
          Выйти
        </button>
      </aside>
      <main className="content full-width-page" id="top">
        <header>
          <div>
            <span className="kicker">TELESCOPE / {pageMeta[0]}</span>
            <h1>{pageMeta[1]}</h1>
            <p>{pageMeta[2]}</p>
          </div>
          <div className="live">
            <i />
            <span>{data.running ? "Сканирование" : "Система готова"}</span>
          </div>
        </header>
        {message && (
          <div className={`notice ${message.type}`}>{message.text}</div>
        )}
        {page === "overview" && <section className="stats">
          <article>
            <div className="stat-icon cyan">
              <Users />
            </div>
            <span>Аккаунты</span>
            <strong>{data.sessions}</strong>
            <small>Сессии в хранилище</small>
          </article>
          <article>
            <div className="stat-icon blue">
              <Activity />
            </div>
            <span>Прогресс</span>
            <strong>{pct}%</strong>
            <small>
              {data.completed || 0} / {data.total || 0} обработано
            </small>
          </article>
          <article>
            <div className="stat-icon purple">
              <Wifi />
            </div>
            <span>Статус</span>
            <strong>
              {data.running
                ? "Работает"
                : data.status === "paused" || data.live?.phase === "paused"
                  ? "Пауза Telegram"
                : data.exit_code > 0
                  ? "Ошибка"
                  : data.status === "completed"
                    ? "Готово"
                    : "Ожидание"}
            </strong>
            <small>{data.process?.log || "SQLite checkpoint"}</small>
          </article>
        </section>}
        {(page === "overview" || page === "parsing") && <section className="progress-card">
          <div className="progress-accent" />
          <div>
            <div>
              <b>{data.live?.phase_label || "Текущая очередь"}</b>
              <span>
                {data.running
                  ? data.live?.current ||
                    `PID ${data.process?.pid} · подготовка`
                  : ["failed", "paused"].includes(data.live?.phase)
                    ? data.live?.error || "Ошибка запуска"
                    : "Нет активного запуска"}
              </span>
              {data.running && total > 0 && (
                <span>
                  {data.live?.phase === "searching"
                    ? `Проверено запросов ${done} из ${total} · найдено сообществ ${data.live?.found ?? 0}`
                    : `Обработано ${done} из ${total} · осталось ${Math.max(0, total - done)}`}
                </span>
              )}
            </div>
            <div className="run-controls">
              <b>{total ? `${pct}%` : "…"}</b>
              {data.running && (
                <button className="pause-control" onClick={pause}>
                  <Pause size={14} />
                  Пауза
                </button>
              )}
              {!data.running && total > done && ["running", "paused"].includes(data.status) && (
                <button className="resume" onClick={resume} disabled={busy}>
                  <Play size={14} />
                  {busy ? "Продолжаем…" : "Продолжить"}
                </button>
              )}
            </div>
          </div>
          <div className="progress">
            <i style={{ width: `${pct}%` }} />
          </div>
          <div className="phase-track" aria-label="Этапы сканирования">
            {[
              ["connecting", "Подключение"],
              ["searching", "Поиск"],
              ["processing", "Анализ"],
              ["exporting", "Отчёт"],
            ].map(([phase, label]) => {
              const phases = ["connecting", "searching", "processing", "exporting", "completed"];
              const current = data.live?.phase === "paused"
                ? phases.indexOf("processing")
                : phases.indexOf(data.live?.phase);
              const position = phases.indexOf(phase);
              return (
                <span
                  key={phase}
                  className={current >= position ? "active" : ""}
                >
                  <i /> {label}
                </span>
              );
            })}
          </div>
        </section>}
        {page === "overview" && (
          <section className="quick-grid">
            <a href="/parsing"><Play /><span><b>Новый парсинг</b><small>Запустить или продолжить поиск</small></span><ArrowRight /></a>
            <a href="/results"><BarChart3 /><span><b>Открыть результаты</b><small>Таблица собранных сообществ</small></span><ArrowRight /></a>
            <a href="/accounts"><Users /><span><b>Управлять аккаунтами</b><small>{accounts.length} Telegram-сессий подключено</small></span><ArrowRight /></a>
          </section>
        )}
        {page === "parsing" && <section className="panel page-panel" id="scan">
          <div className="panel-title">
            <div>
              <span className="kicker">NEW INTELLIGENCE RUN</span>
              <h2>Новое сканирование</h2>
            </div>
            <span className="pill">
              <ShieldCheck size={14} /> MULTI-SESSION
            </span>
          </div>
          <form ref={form} onSubmit={start}>
            <div className="form-step">
              <span>01</span>
              <div><b>Источники</b><small>Проверьте аккаунты и выберите список запросов</small></div>
            </div>
            <div className="scan-source-grid">
              <article className="account-source-card">
                <span><Users size={20} /></span>
                <div>
                  <b>{accounts.filter((a) => a.role === "parser").length} аккаунтов для парсинга</b>
                  <small>{accounts.filter((a) => a.role === "parser" && a.status === "ready").length} готовы к работе</small>
                </div>
                <a href="/accounts">Управлять</a>
              </article>
              <Drop
                name="keywords"
                accept=".txt"
                icon={FileText}
                title={keywordName || "Ключевые слова"}
                subtitle="TXT · один запрос на строку"
                onChange={(e) => setKeywordName(e.target.files[0]?.name || "")}
              />
            </div>
            <div className="form-step">
              <span>02</span>
              <div><b>Фильтры</b><small>Настройте качество будущей выборки</small></div>
            </div>
            <div className="fields">
              <label>
                Мин. участников
                <input
                  type="number"
                  name="min_users"
                  defaultValue="1"
                  min="0"
                />
              </label>
              <label>
                Мин. сообщений / 24ч
                <input
                  type="number"
                  name="min_messages"
                  defaultValue="0"
                  min="0"
                />
              </label>
              <label>
                Язык
                <select name="language" defaultValue="">
                  <option value="">Любой</option>
                  <option value="ru">Русский</option>
                  <option value="uk">Украинский</option>
                  <option value="en">Английский</option>
                </select>
              </label>
              <label>
                Исключающие слова
                <input name="exclude" placeholder="casino, spam" />
              </label>
            </div>
            <div className="checks">
              <label>
                <input type="checkbox" name="active_only" />
                <span>Только активные</span>
              </label>
              <label>
                <input type="checkbox" name="public_only" />
                <span>Только публичные</span>
              </label>
              <label>
                <input type="checkbox" name="writable_only" />
                <span>Можно писать</span>
              </label>
            </div>
            <button className="launch" disabled={busy || data.running}>
              {busy
                ? "Запуск…"
                : data.running
                  ? "Сканирование идёт"
                  : "Запустить сканирование"}
              <ArrowRight size={18} />
            </button>
          </form>
        </section>}
        {page === "runs" && <section className="panel page-panel" id="runs">
          <div className="panel-title">
            <div>
              <span className="kicker">RUN HISTORY</span>
              <h2>История запусков</h2>
            </div>
            <span className="pill">{runs.length} запусков</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Начало</th>
                  <th>Статус</th>
                  <th>Прогресс</th>
                  <th>Результаты</th>
                  <th>Ошибки</th>
                </tr>
              </thead>
              <tbody>
                {runs.length ? (
                  runs.map((r) => (
                    <tr key={r.id}>
                      <td>#{r.id}</td>
                      <td>{fmtDate(r.started_at)}</td>
                      <td>
                        <span className={`status ${r.status}`}>{r.status}</span>
                      </td>
                      <td>
                        {r.completed}/{r.total}
                      </td>
                      <td>{Math.max(r.results_count || 0, r.candidates_count || 0)}</td>
                      <td>{r.errors_count}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="6" className="empty">
                      Запусков пока нет
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>}
        {page === "accounts" && <section className="panel page-panel" id="accounts">
          <div className="panel-title">
            <div>
              <span className="kicker">ACCOUNT POOL</span>
              <h2>Telegram-аккаунты</h2>
            </div>
            <span className="pill">{accounts.filter((a) => a.status === "ready").length} доступны · {accounts.filter((a) => a.status === "sleeping").length} спят</span>
          </div>
          {accounts.some((a) => a.status === "sleeping") && <div className="sleep-notice"><Moon size={18}/><div><b>Некоторые аккаунты отдыхают после FloodWait</b><small>Парсер автоматически пропустит их и снова подключит после окончания cooldown.</small></div></div>}
          <div className="accounts-split"><div className="account-side"><div className="side-title"><Users size={18}/><div><b>Добавление аккаунтов</b><small>Авторизация и действующие сессии</small></div></div><PhoneAuth onDone={refresh} onMessage={setMessage} />
          <div className="account-list">
            {accounts.length ? (
              accounts.map((a, i) => (
                <article key={a.name}>
                  <span className="avatar">{i + 1}</span>
                  <div>
                    <b>Аккаунт {i + 1}</b>
                    <small>
                      {a.name} · {fmtSize(a.size)} · {a.proxy ? `прокси ${a.proxy.host}:${a.proxy.port}` : "без прокси"}
                    </small>
                  </div>
                  <label className="account-role">
                    <span>Назначение</span>
                    <select value={a.role || "parser"} onChange={(e) => assignRole(a.name, e.target.value)} disabled={data.running}>
                      <option value="parser">Парсинг</option>
                      <option value="outreach">Рассылки</option>
                      <option value="autoresponder">Автоответчик</option>
                      <option value="reserve">Резерв</option>
                    </select>
                  </label>
                  {a.status === "sleeping" ? <span className="status sleeping" title={`Пробуждение: ${fmtDate(a.wakes_at)}`}><Moon size={12}/>спит ещё {fmtDuration(a.cooldown_seconds)}</span> : <span className="status ready">готов</span>}
                  <button
                    className="icon-danger"
                    onClick={() => removeAccount(a.name)}
                    title="Удалить"
                  >
                    <Trash2 size={16} />
                  </button>
                </article>
              ))
            ) : (
              <div className="empty">
                Добавьте ZIP, .session или авторизуйтесь по номеру
              </div>
            )}
          </div></div><div className="proxy-side"><ProxySettings values={proxies} onDone={refresh} onMessage={setMessage}/></div></div>
        </section>}
        {page === "logs" && <section className="panel page-panel" id="logs">
          <div className="panel-title">
            <div>
              <span className="kicker">LIVE OUTPUT</span>
              <h2>Логи парсера</h2>
            </div>
            <div className="log-actions">
              <select
                value={logs.selected}
                onChange={(e) => loadLog(e.target.value)}
              >
                {logs.files.map((x) => (
                  <option key={x.name}>{x.name}</option>
                ))}
              </select>
              {logs.selected && (
                <a href={`/download/logs/${encodeURIComponent(logs.selected)}`}>
                  <Download size={15} />
                  Скачать
                </a>
              )}
            </div>
          </div>
          <pre className="terminal">
            {logs.content || "Лог появится после запуска сканирования."}
          </pre>
        </section>}
        {page === "artifacts" && <section className="panel page-panel" id="files">
          <div className="panel-title">
            <div>
              <span className="kicker">ARTIFACTS</span>
              <h2>Артефакты</h2>
            </div>
          </div>
          <div className="actions">
            <a href="/results">
              <BarChart3 />
              Открыть таблицу результатов
            </a>
            <a
              className={!data.report ? "disabled" : ""}
              href="/download/report"
            >
              <Download />
              Скачать Excel
            </a>
            <a
              className={!data.database ? "disabled" : ""}
              href="/download/database"
            >
              <Database />
              Скачать SQLite
            </a>
            <button className="danger" onClick={clear}>
              <Trash2 />
              Удалить все сессии
            </button>
          </div>
        </section>}
      </main>
    </div>
  );
}
function ResultsPage() {
  const [data, setData] = useState({
      rows: [],
      errors: [],
      runs: [],
      total: 0,
      run_id: null,
    }),
    [query, setQuery] = useState(""),
    [runId, setRunId] = useState(""),
    [updated, setUpdated] = useState(null),
    [view, setView] = useState(localStorage.getItem("results-view") || "normal");
  async function load(run = runId, q = query) {
    const params = new URLSearchParams({ limit: "1000" });
    if (run) params.set("run_id", run);
    if (q) params.set("q", q);
    setData(await api(`/api/results?${params}`));
    setUpdated(new Date());
  }
  useEffect(() => {
    load(runId, query);
    const timer = setInterval(() => load(runId, query), 2000);
    return () => clearInterval(timer);
  }, [runId, query]);
  const csv = new URLSearchParams();
  if (data.run_id) csv.set("run_id", data.run_id);
  if (query) csv.set("q", query);
  return (
    <main className="results-page full-width-page">
      <header>
        <Logo />
        <div>
          <a href="/">← Панель управления</a>
          <h1>Результаты парсинга</h1>
          <p>
            Уже собранные данные сохраняются здесь даже при остановке запуска.
          </p>
        </div>
      </header>
      <section className="results-overview">
        <article><span>Найдено</span><strong>{data.total}</strong><small>сообществ в выборке</small></article>
        <article><span>Ошибки</span><strong>{data.errors.length}</strong><small>недоступно или отфильтровано</small></article>
        <article><span>Обновление</span><strong>{updated ? updated.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "—"}</strong><small>данные обновляются автоматически</small></article>
      </section>
      <div className="view-switch" role="tablist" aria-label="Режим таблицы">
        <button className={view === "normal" ? "active" : ""} onClick={() => { setView("normal"); localStorage.setItem("results-view", "normal"); }}>Обычный вид</button>
        <button className={view === "excel" ? "active" : ""} onClick={() => { setView("excel"); localStorage.setItem("results-view", "excel"); }}>Excel-вид</button>
      </div>
      {view === "excel" ? <ExcelView runs={data.runs} initialRun={data.run_id} /> : <>
      <section className="result-tools">
        <select
          value={runId || data.run_id || ""}
          onChange={(e) => {
            setRunId(e.target.value);
            load(e.target.value, query);
          }}
        >
          {data.runs.map((r) => (
            <option key={r.id} value={r.id}>
              Запуск #{r.id} · {fmtDate(r.started_at)}
            </option>
          ))}
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          placeholder="Поиск по названию или username"
        />
        <button onClick={() => load()}>Найти</button>
        <a href={`/download/results.csv?${csv}`}>
          <Download size={16} />
          CSV
        </a>
        <a href="/download/report">
          <Download size={16} />
          Excel
        </a>
      </section>
      <div className="result-summary">
        <span className="live-dot" /> LIVE · строк: <b>{data.total}</b> ·
        ошибок/отфильтровано: <b>{data.errors.length}</b> · обновлено:{" "}
        <b>{updated ? updated.toLocaleTimeString("ru-RU") : "—"}</b>
      </div>
      <section className="result-table">
        <table>
          <thead>
            <tr>
              <th>Сообщество</th>
              <th>Статус</th>
              <th>Тип</th>
              <th>Участники</th>
              <th>24 часа</th>
              <th>7 дней</th>
              <th>30 дней</th>
              <th>Авторы</th>
              <th>Просмотры</th>
              <th>Реакции</th>
              <th>ER</th>
              <th>Рейтинг</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.chat_id}>
                <td>
                  <b>{r.title}</b>
                  {r.username && (
                    <a href={`https://t.me/${r.username}`} target="_blank">
                      @{r.username}
                    </a>
                  )}
                </td>
                <td>
                  <span className={`status ${r.status === "processed" ? "ready" : "running"}`}>
                    {r.status === "processed" ? "Обработано" : "Найдено"}
                  </span>
                </td>
                <td>{r.chat_type}</td>
                <td>{r.participants ?? "—"}</td>
                <td>{r.messages_24h}</td>
                <td>{r.messages_7d}</td>
                <td>{r.messages_30d}</td>
                <td>{r.active_authors}</td>
                <td>{r.views}</td>
                <td>{r.reactions}</td>
                <td>{r.engagement_rate}</td>
                <td>{r.score}</td>
              </tr>
            ))}
            {!data.rows.length && (
              <tr>
                <td colSpan="12" className="empty">
                  В выбранном запуске пока нет результатов
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
      </>}
    </main>
  );
}
export default function App() {
  const [loading, setLoading] = useState(true),
    [user, setUser] = useState(null);
  useEffect(() => {
    api("/api/session")
      .then((x) => {
        setCsrf(x.csrf);
        setUser(x.authenticated ? x.username : null);
      })
      .finally(() => setLoading(false));
  }, []);
  async function logout() {
    try {
      await api("/api/logout", { method: "POST" });
    } finally {
      setUser(null);
      const s = await api("/api/session");
      setCsrf(s.csrf);
    }
  }
  if (loading)
    return (
      <div className="splash">
        <Logo />
      </div>
    );
  if (!user) return <Login onLogin={(x) => setUser(x.username)} />;
  return location.pathname === "/results" ? (
    <ResultsPage />
  ) : (
    <Dashboard user={user} onLogout={logout} />
  );
}
