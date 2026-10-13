// Eden Trader: the phone app. Three tabs (Chart, Calls, History) read the trading server's API; the notifications
// come from the native service (TraderService.java), which reads the same server and key from the app's storage.
'use strict';

const DEFAULT_SERVER = 'https://trade.munimo.online';
const P = () => (window.Capacitor && Capacitor.Plugins) || {};
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (x, d = 2) => (x == null || isNaN(x)) ? '-' : Number(x).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
const pts = (x) => (x == null || isNaN(x)) ? '-' : (x > 0 ? '+' : '') + Math.round(x);

let cfg = { server: '', key: '' };
let view = 'chart';
let histFilter = 'ALL';
let histShown = 60;
let history = null;
let timer = null;

// ---------------- settings (Capacitor Preferences = the native service's storage; localStorage in a browser) -----
async function getPref(k) {
  const Pr = P().Preferences;
  if (Pr) { const r = await Pr.get({ key: k }); return r && r.value || ''; }
  try { return localStorage.getItem(k) || ''; } catch (e) { return ''; }
}
async function setPref(k, v) {
  const Pr = P().Preferences;
  if (Pr) return Pr.set({ key: k, value: v });
  try { localStorage.setItem(k, v); } catch (e) { /* private mode */ }
}
async function loadCfg() {
  cfg.server = (await getPref('server')) || DEFAULT_SERVER;
  cfg.key = await getPref('key');
}
const ready = () => cfg.server && cfg.key;
const api = (path) => cfg.server.replace(/\/+$/, '') + path + (path.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(cfg.key);

async function getJSON(path) {
  const r = await fetch(api(path), { cache: 'no-store' });
  if (r.status === 403) throw new Error('The server refused the key: check it in Settings.');
  if (!r.ok) throw new Error('Server error ' + r.status);
  return r.json();
}
function live(ok, msg) {
  const el = $('live');
  el.className = 'live ' + (ok ? 'ok' : 'bad');
  el.title = msg || (ok ? 'connected' : 'not connected');
}

// ---------------- views ----------------
function show(v) {
  view = v;
  for (const s of document.querySelectorAll('.view')) s.classList.add('hidden');
  $('v-' + v).classList.remove('hidden');
  for (const b of document.querySelectorAll('nav button')) b.classList.toggle('on', b.dataset.v === v);
  refresh();
}

function chartView() {
  const f = $('chart-frame');
  $('chart-empty').classList.toggle('hidden', !!ready());
  f.classList.toggle('hidden', !ready());
  if (!ready()) return;
  const src = cfg.server.replace(/\/+$/, '') + '/?key=' + encodeURIComponent(cfg.key);
  if (f.dataset.src !== src) { f.src = src; f.dataset.src = src; }
}

function tgts(c) {
  // T1 / T2 / T3: the next price levels ahead of the entry, for reference (the exits don't use them)
  if (!c.targets) return '-';
  return c.targets.map((v, k) => `<span class="${c.hit && c.hit[k] ? 'ok' : ''}">T${k + 1} ${num(v, 0)}${c.hit && c.hit[k] ? ' ✓' : ''}</span>`).join(' · ');
}

function callCard(c) {
  const side = c.side === 'BUY' ? 'buy' : 'sell';
  const res = c.open ? `<span class="open">open</span>` : `<b class="${c.pts > 0 ? 'ok' : 'no'}">${pts(c.pts)} pts</b>`;
  const hit = c.success ? `<span class="ok">✓ reached ${c.need} pts</span>` : (c.stopped ? `<span class="no">stop hit before ${c.need} pts</span>` : `<span class="muted">needs ${c.need} pts</span>`);
  return `<div class="call">
    <div class="row"><div><span class="badge ${side}">${c.side}</span> <b>${esc(c.time)}</b> <span class="muted">${esc(c.setup)}</span></div><div>${res}</div></div>
    <div class="kv">
      <span>Entry</span><span>${num(c.entry)} · ${esc(c.option || '')}</span>
      <span>Stop</span><span>${num(c.stop)}${c.open && c.stop_now !== c.stop ? ' → now ' + num(c.stop_now) : ''}</span>
      <span>Status</span><span>${esc(c.status)}</span>
      <span>Targets</span><span>${tgts(c)}</span>
      <span>Went its way</span><span>${pts(c.mfe)} pts · ${hit}</span>
      <span>Went against</span><span>${c.mae == null ? '-' : '-' + Math.round(c.mae)} pts</span>
    </div></div>`;
}

async function callsView() {
  if (!ready()) { $('calls').innerHTML = '<div class="empty">Set the server and key in Settings (⚙) first.</div>'; return; }
  try {
    const [st, ev] = await Promise.all([getJSON('/api/state'), getJSON('/api/events?since=0')]);
    live(true, 'updated ' + st.updated);
    const parts = [];
    for (const n of ['nifty', 'sensex']) {
      const d = st.indices[n];
      if (!d) continue;
      const calls = d.calls || [];
      parts.push(`<div class="card">
        <div class="row"><div class="idx">${esc(d.name)}</div><div class="price">${num(d.last)}</div></div>
        <div class="status">${esc(d.day || '')} · ${calls.length ? calls.length + ' call' + (calls.length > 1 ? 's' : '') + ' today' : 'no call yet today'} · updated ${esc(d.updated || '')}</div>
        ${calls.slice().reverse().map(callCard).join('')}
        ${d.plan ? `<details><summary>Today's plan</summary><pre>${esc(d.plan)}</pre></details>` : ''}
      </div>`);
    }
    $('calls').innerHTML = parts.join('') || '<div class="empty">The server has no data yet today.</div>';
    const evs = (ev.events || []).slice().reverse().slice(0, 30);
    $('feed').innerHTML = evs.map((e) => `<div class="ev"><div class="t">${esc(e.title)}</div><div class="when">${esc(e.at)}</div>
      <div class="small">${esc(e.text).slice(0, 400)}</div></div>`).join('') || '<p class="muted">No alerts yet.</p>';
  } catch (e) {
    live(false, e.message);
    $('calls').innerHTML = `<div class="empty">${esc(e.message || 'Cannot reach the server.')}</div>`;
  }
}

function statCard(label, s) {
  const a = s.all, l = s.last30;
  const tr = a.t1 == null ? '' : `<div class="lbl">T1 ${a.t1}% · T2 ${a.t2}% · T3 ${a.t3}%</div>`;
  const ud = a.up == null ? '' : `<div class="lbl">avg <span class="ok">+${a.up}</span> / <span class="no">-${a.down}</span> pts</div>`;
  return `<div class="stat"><div class="lbl">${label}</div><div class="big">${a.rate == null ? '-' : a.rate + '%'}</div>
    <div class="lbl">${a.success}/${a.calls} calls · ${pts(a.pts)} pts</div>${ud}${tr}
    <div class="lbl">last 30 days ${l.rate == null ? '-' : l.rate + '%'} (${l.success}/${l.calls})</div></div>`;
}

function renderHistory() {
  if (!history) return;
  const r = history.rule || {};
  $('rule').textContent = `A call is a success when the index went at least ${r.NIFTY || 50} points (Nifty) / ${r.SENSEX || 150} points (Sensex) its way before the stop loss. Points = the call's result after costs. avg + / - = how far the index went its way (before the stop) and against it (while the call was open). T1-T3 = how often the next three price levels were reached.`;
  $('stats').innerHTML = statCard('All', history.stats.ALL) + statCard('Nifty', history.stats.NIFTY) + statCard('Sensex', history.stats.SENSEX);
  const rows = history.calls.filter((c) => histFilter === 'ALL' || c.index === histFilter);
  let html = '', day = '';
  for (const c of rows.slice(0, histShown)) {
    if (c.d !== day) { day = c.d; html += `<div class="day">${esc(new Date(day + 'T00:00:00').toDateString())}</div>`; }
    html += `<div class="h"><div class="mark ${c.success ? 'ok' : 'no'}">${c.success ? '✓' : '✗'}</div>
      <div><b>${esc(c.index)}</b> <span class="badge ${c.side === 'BUY' ? 'buy' : 'sell'}">${c.side}</span> ${esc(c.time)}
        <div class="sub">${esc(c.setup)} at ${num(c.entry)} · <span class="ok">${pts(c.mfe)}</span> / <span class="no">-${Math.round(c.mae || 0)}</span>${c.hit ? ' · ' + c.hit.map((h, k) => 'T' + (k + 1) + (h ? '✓' : '·')).join(' ') : ''}</div></div>
      <div class="pts ${c.pts > 0 ? 'ok' : 'no'}">${pts(c.pts)}</div></div>`;
  }
  $('hist').innerHTML = html || '<p class="muted">No calls yet.</p>';
  $('more').classList.toggle('hidden', rows.length <= histShown);
}

async function historyView() {
  if (!ready()) { $('hist').innerHTML = '<div class="empty">Set the server and key in Settings (⚙) first.</div>'; return; }
  try {
    history = await getJSON('/api/history');
    live(true);
    renderHistory();
  } catch (e) {
    live(false, e.message);
    $('hist').innerHTML = `<div class="empty">${esc(e.message || 'Cannot reach the server.')}</div>`;
  }
}

function settingsView() {
  $('s-server').value = cfg.server || DEFAULT_SERVER;
  $('s-key').value = cfg.key || '';
}

async function refresh() {
  if (view === 'chart') chartView();
  else if (view === 'calls') await callsView();
  else if (view === 'history') await historyView();
  else if (view === 'settings') settingsView();
}

// ---------------- notifications (the native service sends them; this asks for permission and tests) ----------
async function askPermission() {
  const LN = P().LocalNotifications;
  if (!LN) { $('s-msg').textContent = 'Notifications work in the installed app.'; return; }
  const r = await LN.requestPermissions();
  $('s-msg').textContent = r.display === 'granted' ? 'Notifications are on.' : 'Notifications are off: allow them in the phone settings.';
}
async function testNotification() {
  const LN = P().LocalNotifications;
  if (!LN) { $('s-msg').textContent = 'Notifications work in the installed app.'; return; }
  await askPermission();
  await LN.schedule({ notifications: [{ id: 7, title: 'Eden Trader', body: 'Test: calls will arrive like this.', schedule: { at: new Date(Date.now() + 1500) } }] });
}

// ---------------- start ----------------
async function main() {
  await loadCfg();
  for (const b of document.querySelectorAll('nav button')) b.onclick = () => show(b.dataset.v);
  $('gear').onclick = () => show('settings');
  for (const b of document.querySelectorAll('.filter button')) {
    b.onclick = () => {
      histFilter = b.dataset.f; histShown = 60;
      for (const x of document.querySelectorAll('.filter button')) x.classList.toggle('on', x === b);
      renderHistory();
    };
  }
  $('more').onclick = () => { histShown += 60; renderHistory(); };
  $('s-perm').onclick = askPermission;
  $('s-test').onclick = testNotification;
  $('s-save').onclick = async () => {
    cfg.server = ($('s-server').value || DEFAULT_SERVER).trim().replace(/\/+$/, '');
    if (!/^https?:\/\//.test(cfg.server)) cfg.server = 'https://' + cfg.server;
    cfg.key = $('s-key').value.trim();
    await setPref('server', cfg.server);
    await setPref('key', cfg.key);
    $('s-msg').textContent = 'Checking ...';
    try {
      await getJSON('/api/state');
      $('s-msg').textContent = 'Connected. Calls will arrive as notifications.';
      await askPermission();
      show('calls');
    } catch (e) {
      $('s-msg').textContent = e.message || 'Cannot reach the server.';
    }
  };
  timer = setInterval(() => { if (!document.hidden && view === 'calls') callsView(); }, 10000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  if (!ready()) { show('settings'); return; }
  show('calls');
  askPermission().catch(() => {});
}
main();
