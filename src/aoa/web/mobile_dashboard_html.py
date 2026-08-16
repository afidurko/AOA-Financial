"""Mobile dashboard HTML — Ant Design Mobile shell over AOA REST API."""

# Published antd-mobile via ESM CDN (no Node build). Sibling fork is optional.
MOBILE_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta name="theme-color" content="#0f1419"/>
  <meta name="apple-mobile-web-app-capable" content="yes"/>
  <title>AOA Mobile</title>
  <link rel="stylesheet" href="https://esm.sh/antd-mobile@5.37.1/es/global/global.css"/>
  <style>
    :root {
      --bg:#0f1419; --surface:#1a2332; --border:#2d3a4f;
      --text:#e7ecf3; --muted:#8b9cb3; --accent:#3b82f6;
      --green:#22c55e; --red:#ef4444; --amber:#f59e0b;
      --adm-color-primary: #3b82f6;
      --adm-color-success: #22c55e;
      --adm-color-warning: #f59e0b;
      --adm-color-danger: #ef4444;
      --adm-color-text: #e7ecf3;
      --adm-color-text-secondary: #8b9cb3;
      --adm-color-background: #0f1419;
      --adm-color-box: #1a2332;
      --adm-color-border: #2d3a4f;
      --adm-border-color: #2d3a4f;
    }
    *{box-sizing:border-box}
    html,body,#root{height:100%;margin:0}
    body{
      font-family:ui-sans-serif,system-ui,sans-serif;
      background:var(--bg);color:var(--text);
      -webkit-tap-highlight-color:transparent;
    }
    .app-shell{min-height:100%;display:flex;flex-direction:column;background:var(--bg)}
    .app-body{flex:1;overflow:auto;padding:12px 12px 72px;padding-bottom:calc(72px + env(safe-area-inset-bottom))}
    .stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
    .stat{
      background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px
    }
    .stat label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:6px}
    .stat strong{font-size:1.25rem}
    .actions{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 14px}
    .muted{color:var(--muted);font-size:13px}
    .row-ok{color:var(--green)}.row-block{color:var(--red)}
    a.desk{color:var(--accent);font-size:13px;text-decoration:none}
    .adm-list{--border-inner: solid 1px var(--border);--border-top: solid 1px var(--border);--border-bottom: solid 1px var(--border);background:var(--surface)}
    .adm-list-item{background:var(--surface);color:var(--text)}
    .adm-navbar{background:var(--surface);border-bottom:1px solid var(--border);color:var(--text)}
    .adm-tab-bar{background:var(--surface);border-top:1px solid var(--border);padding-bottom:env(safe-area-inset-bottom)}
    .adm-button{border-radius:8px}
    .badge{
      display:inline-block;padding:.1rem .45rem;border-radius:999px;font-size:.7rem;font-weight:600;
      text-transform:uppercase;margin-left:8px;vertical-align:middle
    }
    .badge-paper{background:#1e3a5f;color:#93c5fd}
    .badge-live{background:#450a0a;color:#fca5a5}
    .badge-dry{background:#422006;color:#fcd34d}
  </style>
  <script type="importmap">
  {
    "imports": {
      "react": "https://esm.sh/react@18.3.1",
      "react/jsx-runtime": "https://esm.sh/react@18.3.1/jsx-runtime",
      "react-dom": "https://esm.sh/react-dom@18.3.1",
      "react-dom/client": "https://esm.sh/react-dom@18.3.1/client",
      "antd-mobile": "https://esm.sh/antd-mobile@5.37.1?deps=react@18.3.1,react-dom@18.3.1",
      "antd-mobile-icons": "https://esm.sh/antd-mobile-icons@0.3.0"
    }
  }
  </script>
</head>
<body>
  <div id="root"></div>
  <script type="module">
    import React, { useCallback, useEffect, useState } from 'react';
    import { createRoot } from 'react-dom/client';
    import {
      NavBar, TabBar, List, Button, Tag, Toast, DotLoading, ErrorBlock, Space
    } from 'antd-mobile';
    import {
      AppOutline, UnorderedListOutline, PayCircleOutline, CheckShieldOutline
    } from 'antd-mobile-icons';

    const h = React.createElement;
    const fmt = (n) => n == null ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });

    async function api(path, opts) {
      const r = await fetch(path, opts);
      if (!r.ok) {
        let detail = r.statusText;
        try { detail = (await r.json()).detail || detail; } catch (_) {}
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      }
      return r.json();
    }

    function ModeBadge({ mode }) {
      const cls = mode === 'live' ? 'badge-live' : mode === 'dry-run' ? 'badge-dry' : 'badge-paper';
      return h('span', { className: 'badge ' + cls }, mode || '…');
    }

    function HomeTab({ status, config, busy, onAction }) {
      const acct = status?.account || {};
      const loop = status?.loop || {};
      return h('div', null,
        h('div', { className: 'muted' },
          'Market: ', status?.market_open ? 'OPEN' : 'CLOSED',
          ' · ', status?.broker || '—',
          ' · ',
          h('a', { className: 'desk', href: '/' }, 'Desktop')
        ),
        h('div', { className: 'stat-grid' },
          h('div', { className: 'stat' }, h('label', null, 'Equity'), h('strong', null, fmt(acct.equity))),
          h('div', { className: 'stat' }, h('label', null, 'Cash'), h('strong', null, fmt(acct.settled_cash))),
          h('div', { className: 'stat' },
            h('label', null, 'Loop'),
            h('strong', null, loop.running ? 'Running' : 'Stopped'),
            h('div', { className: 'muted' }, loop.last_cycle_at || loop.last_error || '—')
          ),
          h('div', { className: 'stat' },
            h('label', null, 'Mode'),
            h('strong', null, status?.mode || '—')
          )
        ),
        h('div', { className: 'actions' },
          h(Button, { color: 'primary', size: 'small', loading: busy, onClick: () => onAction('run') }, 'Run cycle'),
          h(Button, { fill: 'outline', size: 'small', disabled: busy, onClick: () => onAction('start') }, 'Start loop'),
          h(Button, { color: 'danger', fill: 'outline', size: 'small', disabled: busy, onClick: () => onAction('stop') }, 'Stop loop'),
          h(Button, { fill: 'outline', size: 'small', disabled: busy, onClick: () => onAction('refresh') }, 'Refresh')
        ),
        config?.antd_mobile_url
          ? h('p', { className: 'muted' },
              h('a', { className: 'desk', href: config.antd_mobile_url, target: '_blank', rel: 'noopener' },
                'antd-mobile fork ↗'))
          : null
      );
    }

    function TeamTab({ last }) {
      const r = last?.result || {};
      const roster = [
        { name: 'Bob', role: 'Health', summary: r.health?.summary },
        { name: 'Tom', role: 'Trends', summary: (r.trends || []).length + ' reports' },
        { name: 'Julie', role: 'Algorithms', summary: (r.algorithms || []).length + ' reports' },
        { name: 'Morgan', role: 'Volume & Options', summary: (r.market_contexts || []).length + ' reports' },
        { name: 'Hailey', role: 'Catalysts', summary: (r.catalysts || []).length + ' reports' },
        { name: 'Alan', role: 'Decision', summary: r.decision?.summary },
        { name: 'Andrea', role: 'Risk', summary: (r.risk_plans || []).length + ' plans' },
        { name: 'Aaron', role: 'CEO', summary: r.ceo?.summary },
        { name: 'Alex', role: 'Assistant', summary: r.assistant?.focus },
      ];
      if (!last?.result) {
        return h('p', { className: 'muted' }, 'Run a cycle to populate the roster.');
      }
      return h(List, { header: 'Team roster' },
        roster.map((m) => h(List.Item, {
          key: m.name,
          description: m.summary || '—',
        }, m.name + ' · ' + m.role))
      );
    }

    function TradesTab({ status, last }) {
      const positions = status?.positions || [];
      const proposals = last?.result?.proposals || [];
      return h('div', null,
        h(List, { header: 'Positions' },
          positions.length
            ? positions.map((p) => h(List.Item, {
                key: p.symbol,
                description: 'Qty ' + p.qty + ' · MV ' + fmt(p.market_value),
                extra: h('span', {
                  className: (p.unrealized_pl || 0) >= 0 ? 'row-ok' : 'row-block'
                }, fmt(p.unrealized_pl)),
              }, p.symbol))
            : h(List.Item, null, 'No positions')
        ),
        h(List, { header: 'Proposals', style: { marginTop: 12 } },
          proposals.length
            ? proposals.map((p, i) => h(List.Item, {
                key: i,
                description: (p.strategy || '') + ' · ' + fmt(p.est_notional),
                extra: h(Tag, { color: p.approved ? 'success' : 'danger' }, p.approved ? 'OK' : 'block'),
              }, (p.side || '') + ' ' + (p.symbol || '')))
            : h(List.Item, null, 'No proposals')
        )
      );
    }

    function ApprovalsTab({ items, busy, onResolve }) {
      if (!items.length) {
        return h('p', { className: 'muted' }, 'Approval inbox is empty.');
      }
      return h(List, { header: 'Approval inbox' },
        items.map((item) => h(List.Item, {
          key: item.id || item.ts || JSON.stringify(item).slice(0, 40),
          description: item.summary || item.note || item.symbol || '—',
          extra: h(Space, { direction: 'vertical' },
            h(Button, {
              size: 'mini', color: 'primary', disabled: busy,
              onClick: () => onResolve(item, 'approve'),
            }, 'Approve'),
            h(Button, {
              size: 'mini', color: 'danger', fill: 'outline', disabled: busy,
              onClick: () => onResolve(item, 'reject'),
            }, 'Reject')
          ),
        }, item.title || item.action || item.id || 'Item'))
      );
    }

    function App() {
      const [tab, setTab] = useState('home');
      const [status, setStatus] = useState(null);
      const [config, setConfig] = useState({});
      const [last, setLast] = useState({});
      const [approvals, setApprovals] = useState([]);
      const [busy, setBusy] = useState(false);
      const [error, setError] = useState(null);
      const [loading, setLoading] = useState(true);

      const refresh = useCallback(async () => {
        try {
          const [st, cfg, lc, ap] = await Promise.all([
            api('/api/status'),
            api('/api/config').catch(() => ({})),
            api('/api/last-cycle').catch(() => ({})),
            api('/api/approvals').catch(() => ({ items: [] })),
          ]);
          setStatus(st);
          setConfig(cfg);
          setLast(lc);
          setApprovals(ap.items || []);
          setError(null);
        } catch (e) {
          setError(e.message || String(e));
        } finally {
          setLoading(false);
        }
      }, []);

      useEffect(() => { refresh(); const t = setInterval(refresh, 15000); return () => clearInterval(t); }, [refresh]);

      const onAction = async (kind) => {
        setBusy(true);
        try {
          if (kind === 'run') {
            await api('/api/run', { method: 'POST' });
            Toast.show({ icon: 'success', content: 'Cycle finished' });
          } else if (kind === 'start') {
            await api('/api/loop/start', { method: 'POST' });
            Toast.show({ content: 'Loop started' });
          } else if (kind === 'stop') {
            await api('/api/loop/stop', { method: 'POST' });
            Toast.show({ content: 'Loop stopped' });
          }
          await refresh();
        } catch (e) {
          Toast.show({ icon: 'fail', content: e.message || String(e) });
        } finally {
          setBusy(false);
        }
      };

      const onResolve = async (item, action) => {
        if (!item?.id) {
          Toast.show({ icon: 'fail', content: 'Missing approval id' });
          return;
        }
        const status = action === 'approve' ? 'approved' : 'rejected';
        setBusy(true);
        try {
          await api('/api/approvals/' + encodeURIComponent(item.id) + '/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status }),
          });
          Toast.show({ icon: 'success', content: status === 'approved' ? 'Approved' : 'Rejected' });
          await refresh();
        } catch (e) {
          Toast.show({ icon: 'fail', content: e.message || String(e) });
        } finally {
          setBusy(false);
        }
      };

      const tabs = {
        home: h(HomeTab, { status, config, busy, onAction }),
        team: h(TeamTab, { last }),
        trades: h(TradesTab, { status, last }),
        approvals: h(ApprovalsTab, { items: approvals, busy, onResolve }),
      };

      return h('div', { className: 'app-shell' },
        h(NavBar, { back: null },
          h('span', null, 'AOA Mobile'),
          h(ModeBadge, { mode: status?.mode })
        ),
        h('div', { className: 'app-body' },
          loading ? h('div', { style: { textAlign: 'center', padding: 40 } }, h(DotLoading, { color: 'primary' }))
            : error ? h(ErrorBlock, { status: 'default', title: 'Cannot load status', description: error })
            : tabs[tab]
        ),
        h(TabBar, { activeKey: tab, onChange: setTab, safeArea: true },
          h(TabBar.Item, { key: 'home', icon: h(AppOutline), title: 'Home' }),
          h(TabBar.Item, { key: 'team', icon: h(UnorderedListOutline), title: 'Team' }),
          h(TabBar.Item, { key: 'trades', icon: h(PayCircleOutline), title: 'Trades' }),
          h(TabBar.Item, { key: 'approvals', icon: h(CheckShieldOutline), title: 'Inbox' })
        )
      );
    }

    createRoot(document.getElementById('root')).render(h(App));
  </script>
</body>
</html>
"""
