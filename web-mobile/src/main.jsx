import React, { useCallback, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  NavBar,
  TabBar,
  List,
  Button,
  Tag,
  Toast,
  DotLoading,
  ErrorBlock,
  Space,
} from 'antd-mobile'
import {
  AppOutline,
  UnorderedListOutline,
  PayCircleOutline,
  CheckShieldOutline,
} from 'antd-mobile-icons'
import 'antd-mobile/es/global'
import './styles.css'

const fmt = (n) =>
  n == null
    ? '—'
    : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })

async function api(path, opts) {
  const r = await fetch(path, opts)
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail || detail
    } catch (_) {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return r.json()
}

function ModeBadge({ mode }) {
  const cls =
    mode === 'live' ? 'badge-live' : mode === 'dry-run' ? 'badge-dry' : 'badge-paper'
  return <span className={`badge ${cls}`}>{mode || '…'}</span>
}

function HomeTab({ status, config, busy, onAction }) {
  const acct = status?.account || {}
  const loop = status?.loop || {}
  return (
    <div>
      <div className="muted">
        Market: {status?.market_open ? 'OPEN' : 'CLOSED'} · {status?.broker || '—'} ·{' '}
        <a className="desk" href="/">
          Desktop
        </a>
      </div>
      <div className="stat-grid">
        <div className="stat">
          <label>Equity</label>
          <strong>{fmt(acct.equity)}</strong>
        </div>
        <div className="stat">
          <label>Cash</label>
          <strong>{fmt(acct.settled_cash)}</strong>
        </div>
        <div className="stat">
          <label>Loop</label>
          <strong>{loop.running ? 'Running' : 'Stopped'}</strong>
          <div className="muted">{loop.last_cycle_at || loop.last_error || '—'}</div>
        </div>
        <div className="stat">
          <label>Mode</label>
          <strong>{status?.mode || '—'}</strong>
        </div>
      </div>
      <div className="actions">
        <Button color="primary" size="small" loading={busy} onClick={() => onAction('run')}>
          Run cycle
        </Button>
        <Button fill="outline" size="small" disabled={busy} onClick={() => onAction('start')}>
          Start loop
        </Button>
        <Button
          color="danger"
          fill="outline"
          size="small"
          disabled={busy}
          onClick={() => onAction('stop')}
        >
          Stop loop
        </Button>
        <Button fill="outline" size="small" disabled={busy} onClick={() => onAction('refresh')}>
          Refresh
        </Button>
      </div>
      {config?.antd_mobile_url ? (
        <p className="muted">
          <a className="desk" href={config.antd_mobile_url} target="_blank" rel="noopener noreferrer">
            antd-mobile fork ↗
          </a>
        </p>
      ) : null}
    </div>
  )
}

function TeamTab({ last }) {
  const r = last?.result || {}
  const roster = [
    { name: 'Bob', role: 'Health', summary: r.health?.summary },
    { name: 'Tom', role: 'Trends', summary: `${(r.trends || []).length} reports` },
    { name: 'Julie', role: 'Algorithms', summary: `${(r.algorithms || []).length} reports` },
    {
      name: 'Morgan',
      role: 'Volume & Options',
      summary: `${(r.market_contexts || []).length} reports`,
    },
    { name: 'Hailey', role: 'Catalysts', summary: `${(r.catalysts || []).length} reports` },
    { name: 'Alan', role: 'Decision', summary: r.decision?.summary },
    { name: 'Andrea', role: 'Risk', summary: `${(r.risk_plans || []).length} plans` },
    { name: 'Aaron', role: 'CEO', summary: r.ceo?.summary },
    { name: 'Alex', role: 'Assistant', summary: r.assistant?.focus },
  ]
  if (!last?.result) {
    return <p className="muted">Run a cycle to populate the roster.</p>
  }
  return (
    <List header="Team roster">
      {roster.map((m) => (
        <List.Item key={m.name} description={m.summary || '—'}>
          {m.name} · {m.role}
        </List.Item>
      ))}
    </List>
  )
}

function TradesTab({ status, last }) {
  const positions = status?.positions || []
  const proposals = last?.result?.proposals || []
  return (
    <div>
      <List header="Positions">
        {positions.length ? (
          positions.map((p) => (
            <List.Item
              key={p.symbol}
              description={`Qty ${p.qty} · MV ${fmt(p.market_value)}`}
              extra={
                <span className={(p.unrealized_pl || 0) >= 0 ? 'row-ok' : 'row-block'}>
                  {fmt(p.unrealized_pl)}
                </span>
              }
            >
              {p.symbol}
            </List.Item>
          ))
        ) : (
          <List.Item>No positions</List.Item>
        )}
      </List>
      <List header="Proposals" style={{ marginTop: 12 }}>
        {proposals.length ? (
          proposals.map((p, i) => (
            <List.Item
              key={i}
              description={`${p.strategy || ''} · ${fmt(p.est_notional)}`}
              extra={<Tag color={p.approved ? 'success' : 'danger'}>{p.approved ? 'OK' : 'block'}</Tag>}
            >
              {(p.side || '') + ' ' + (p.symbol || '')}
            </List.Item>
          ))
        ) : (
          <List.Item>No proposals</List.Item>
        )}
      </List>
    </div>
  )
}

function ApprovalsTab({ items, busy, onResolve }) {
  if (!items.length) {
    return <p className="muted">Approval inbox is empty.</p>
  }
  return (
    <List header="Approval inbox">
      {items.map((item) => (
        <List.Item
          key={item.id || item.ts || JSON.stringify(item).slice(0, 40)}
          description={item.summary || item.note || item.symbol || '—'}
          extra={
            <Space direction="vertical">
              <Button
                size="mini"
                color="primary"
                disabled={busy}
                onClick={() => onResolve(item, 'approve')}
              >
                Approve
              </Button>
              <Button
                size="mini"
                color="danger"
                fill="outline"
                disabled={busy}
                onClick={() => onResolve(item, 'reject')}
              >
                Reject
              </Button>
            </Space>
          }
        >
          {item.title || item.action || item.id || 'Item'}
        </List.Item>
      ))}
    </List>
  )
}

function App() {
  const [tab, setTab] = useState('home')
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState({})
  const [last, setLast] = useState({})
  const [approvals, setApprovals] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const [st, cfg, lc, ap] = await Promise.all([
        api('/api/status'),
        api('/api/config').catch(() => ({})),
        api('/api/last-cycle').catch(() => ({})),
        api('/api/approvals').catch(() => ({ items: [] })),
      ])
      setStatus(st)
      setConfig(cfg)
      setLast(lc)
      setApprovals(ap.items || [])
      setError(null)
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 15000)
    return () => clearInterval(t)
  }, [refresh])

  const onAction = async (kind) => {
    setBusy(true)
    try {
      if (kind === 'run') {
        await api('/api/run', { method: 'POST' })
        Toast.show({ icon: 'success', content: 'Cycle finished' })
      } else if (kind === 'start') {
        await api('/api/loop/start', { method: 'POST' })
        Toast.show({ content: 'Loop started' })
      } else if (kind === 'stop') {
        await api('/api/loop/stop', { method: 'POST' })
        Toast.show({ content: 'Loop stopped' })
      }
      await refresh()
    } catch (e) {
      Toast.show({ icon: 'fail', content: e.message || String(e) })
    } finally {
      setBusy(false)
    }
  }

  const onResolve = async (item, action) => {
    if (!item?.id) {
      Toast.show({ icon: 'fail', content: 'Missing approval id' })
      return
    }
    const statusValue = action === 'approve' ? 'approved' : 'rejected'
    setBusy(true)
    try {
      await api(`/api/approvals/${encodeURIComponent(item.id)}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: statusValue }),
      })
      Toast.show({
        icon: 'success',
        content: statusValue === 'approved' ? 'Approved' : 'Rejected',
      })
      await refresh()
    } catch (e) {
      Toast.show({ icon: 'fail', content: e.message || String(e) })
    } finally {
      setBusy(false)
    }
  }

  const tabs = {
    home: <HomeTab status={status} config={config} busy={busy} onAction={onAction} />,
    team: <TeamTab last={last} />,
    trades: <TradesTab status={status} last={last} />,
    approvals: <ApprovalsTab items={approvals} busy={busy} onResolve={onResolve} />,
  }

  return (
    <div className="app-shell">
      <NavBar back={null}>
        <span>AOA Mobile</span>
        <ModeBadge mode={status?.mode} />
      </NavBar>
      <div className="app-body">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <DotLoading color="primary" />
          </div>
        ) : error ? (
          <ErrorBlock status="default" title="Cannot load status" description={error} />
        ) : (
          tabs[tab]
        )}
      </div>
      <TabBar activeKey={tab} onChange={setTab} safeArea>
        <TabBar.Item key="home" icon={<AppOutline />} title="Home" />
        <TabBar.Item key="team" icon={<UnorderedListOutline />} title="Team" />
        <TabBar.Item key="trades" icon={<PayCircleOutline />} title="Trades" />
        <TabBar.Item key="approvals" icon={<CheckShieldOutline />} title="Inbox" />
      </TabBar>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App />)
