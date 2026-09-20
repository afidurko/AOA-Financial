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
  PullToRefresh,
  NoticeBar,
  Empty,
  SwipeAction,
  Avatar,
  Badge,
  CapsuleTabs,
  SafeArea,
} from 'antd-mobile'
import {
  AppOutline,
  UnorderedListOutline,
  PayCircleOutline,
  CheckShieldOutline,
  PlayOutline,
  CloseCircleOutline,
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

function initials(name) {
  return (name || '?').slice(0, 1).toUpperCase()
}

function HomeTab({ status, config, last, brief, busy, onAction }) {
  const acct = status?.account || {}
  const loop = status?.loop || {}
  const assistant = brief || last?.result?.assistant || null
  const must = assistant?.must_do || []
  const focus = assistant?.focus

  return (
    <div className="pane pane-enter">
      <NoticeBar
        content={
          (status?.market_open ? 'Market OPEN' : 'Market CLOSED') +
          ' · ' +
          (status?.broker || '—') +
          ' · pull to refresh'
        }
        color={status?.market_open ? 'info' : 'default'}
        closeable={false}
        icon={null}
      />

      <section className="hero">
        <p className="hero-brand">AOA Financial</p>
        <p className="hero-label">Equity</p>
        <p className="hero-value">{fmt(acct.equity)}</p>
        <p className="hero-sub">
          Cash {fmt(acct.settled_cash)}
          <span className="dot">·</span>
          Loop {loop.running ? 'running' : 'stopped'}
          <span className="dot">·</span>
          <ModeBadge mode={status?.mode} />
        </p>
        {loop.last_error ? <p className="hero-err">{loop.last_error}</p> : null}
        {loop.last_cycle_at && !loop.last_error ? (
          <p className="hero-meta">Last cycle {loop.last_cycle_at}</p>
        ) : null}
      </section>

      <div className="cta-block">
        <Button
          block
          color="primary"
          size="large"
          loading={busy}
          onClick={() => onAction('run')}
        >
          Run cycle
        </Button>
        <div className="cta-row">
          <Button
            fill="outline"
            size="middle"
            disabled={busy || loop.running}
            onClick={() => onAction('start')}
          >
            <Space>
              <PlayOutline /> Start loop
            </Space>
          </Button>
          <Button
            color="danger"
            fill="outline"
            size="middle"
            disabled={busy || !loop.running}
            onClick={() => onAction('stop')}
          >
            <Space>
              <CloseCircleOutline /> Stop
            </Space>
          </Button>
        </div>
      </div>

      <section className="priorities">
        <h2>Alex — priorities</h2>
        {focus ? <p className="focus">Focus: {focus}</p> : null}
        {must.length ? (
          <List>
            {must.slice(0, 5).map((item, i) => (
              <List.Item key={i} description={item.detail || undefined}>
                {item.title || item}
              </List.Item>
            ))}
          </List>
        ) : (
          <Empty
            description="Run a cycle for Alex priorities"
            imageStyle={{ width: 64 }}
          />
        )}
      </section>

      <p className="footer-links">
        <a className="desk" href="/">
          Desktop dashboard
        </a>
        {config?.antd_mobile_url ? (
          <>
            <span className="dot">·</span>
            <a
              className="desk"
              href={config.antd_mobile_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              UI kit ↗
            </a>
          </>
        ) : null}
      </p>
    </div>
  )
}

function TeamTab({ last }) {
  const r = last?.result || {}
  const roster = [
    { name: 'Bob', role: 'Health', summary: r.health?.summary, ok: !!r.health },
    { name: 'Tom', role: 'Trends', summary: `${(r.trends || []).length} reports`, ok: (r.trends || []).length > 0 },
    { name: 'Julie', role: 'Algorithms', summary: `${(r.algorithms || []).length} reports`, ok: (r.algorithms || []).length > 0 },
    { name: 'Morgan', role: 'Volume & Options', summary: `${(r.market_contexts || []).length} reports`, ok: (r.market_contexts || []).length > 0 },
    { name: 'Hailey', role: 'Catalysts', summary: `${(r.catalysts || []).length} reports`, ok: (r.catalysts || []).length > 0 },
    { name: 'Alan', role: 'Decision', summary: r.decision?.summary, ok: !!r.decision },
    { name: 'Andrea', role: 'Risk', summary: `${(r.risk_plans || []).length} plans`, ok: (r.risk_plans || []).length > 0 },
    { name: 'Aaron', role: 'CEO', summary: r.ceo?.summary, ok: !!r.ceo },
    { name: 'Alex', role: 'Assistant', summary: r.assistant?.focus, ok: !!r.assistant },
  ]

  if (!last?.result) {
    return (
      <div className="pane pane-enter">
        <Empty description="Run a cycle to populate the roster" imageStyle={{ width: 72 }} />
      </div>
    )
  }

  return (
    <div className="pane pane-enter">
      <List header="Team roster">
        {roster.map((m) => (
          <List.Item
            key={m.name}
            prefix={
              <Avatar
                style={{
                  '--size': '36px',
                  '--border-radius': '10px',
                  background: m.ok ? 'var(--green-soft)' : 'var(--amber-soft)',
                  color: m.ok ? 'var(--green)' : 'var(--amber)',
                }}
              >
                {initials(m.name)}
              </Avatar>
            }
            description={m.summary || '—'}
            extra={
              <Tag color={m.ok ? 'success' : 'warning'} fill="outline">
                {m.ok ? 'ready' : 'idle'}
              </Tag>
            }
          >
            {m.name}
            <span className="role"> {m.role}</span>
          </List.Item>
        ))}
      </List>
    </div>
  )
}

function TradesTab({ status, last }) {
  const positions = status?.positions || []
  const proposals = last?.result?.proposals || []

  return (
    <div className="pane pane-enter">
      <CapsuleTabs defaultActiveKey="positions">
        <CapsuleTabs.Tab title={`Positions (${positions.length})`} key="positions">
          {positions.length ? (
            <List>
              {positions.map((p) => (
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
              ))}
            </List>
          ) : (
            <Empty description="No open positions" imageStyle={{ width: 64 }} />
          )}
        </CapsuleTabs.Tab>
        <CapsuleTabs.Tab title={`Proposals (${proposals.length})`} key="proposals">
          {proposals.length ? (
            <List>
              {proposals.map((p, i) => (
                <List.Item
                  key={i}
                  description={`${p.strategy || ''} · ${fmt(p.est_notional)}`}
                  extra={
                    <Tag color={p.approved ? 'success' : 'danger'}>
                      {p.approved ? 'OK' : 'block'}
                    </Tag>
                  }
                >
                  {(p.side || '') + ' ' + (p.symbol || '')}
                </List.Item>
              ))}
            </List>
          ) : (
            <Empty description="No proposals yet" imageStyle={{ width: 64 }} />
          )}
        </CapsuleTabs.Tab>
      </CapsuleTabs>
    </div>
  )
}

function ApprovalsTab({ items, busy, onResolve }) {
  const pending = items.filter((i) => !i.status || i.status === 'pending')

  if (!pending.length) {
    return (
      <div className="pane pane-enter">
        <Empty description="Approval inbox is empty" imageStyle={{ width: 72 }} />
      </div>
    )
  }

  return (
    <div className="pane pane-enter">
      <List header={`${pending.length} pending`}>
        {pending.map((item) => (
          <SwipeAction
            key={item.id || item.ts || JSON.stringify(item).slice(0, 40)}
            rightActions={[
              {
                key: 'approve',
                text: 'Approve',
                color: 'primary',
                onClick: () => onResolve(item, 'approve'),
              },
              {
                key: 'reject',
                text: 'Reject',
                color: 'danger',
                onClick: () => onResolve(item, 'reject'),
              },
            ]}
          >
            <List.Item
              description={item.summary || item.note || item.symbol || '—'}
              disabled={busy}
              clickable={false}
            >
              {item.title || item.action || item.id || 'Item'}
            </List.Item>
          </SwipeAction>
        ))}
      </List>
      <p className="muted swipe-hint">Swipe left to approve or reject</p>
    </div>
  )
}

function App() {
  const [tab, setTab] = useState('home')
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState({})
  const [last, setLast] = useState({})
  const [brief, setBrief] = useState(null)
  const [approvals, setApprovals] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const [st, cfg, lc, ap, ab] = await Promise.all([
        api('/api/status'),
        api('/api/config').catch(() => ({})),
        api('/api/last-cycle').catch(() => ({})),
        api('/api/approvals').catch(() => ({ items: [] })),
        api('/api/assistant/brief').catch(() => null),
      ])
      setStatus(st)
      setConfig(cfg)
      setLast(lc)
      setApprovals(ap.items || [])
      setBrief(ab)
      setError(null)
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 20000)
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

  const pendingCount = approvals.filter((i) => !i.status || i.status === 'pending').length

  const tabs = {
    home: (
      <HomeTab
        status={status}
        config={config}
        last={last}
        brief={brief}
        busy={busy}
        onAction={onAction}
      />
    ),
    team: <TeamTab last={last} />,
    trades: <TradesTab status={status} last={last} />,
    approvals: <ApprovalsTab items={approvals} busy={busy} onResolve={onResolve} />,
  }

  return (
    <div className="app-shell">
      <SafeArea position="top" />
      <NavBar back={null} className="top-nav">
        <span className="nav-title">AOA</span>
        <ModeBadge mode={status?.mode} />
      </NavBar>
      <PullToRefresh onRefresh={refresh}>
        <div className="app-body">
          {loading ? (
            <div className="loading-wrap">
              <DotLoading color="primary" />
            </div>
          ) : error ? (
            <ErrorBlock
              status="default"
              title="Cannot load status"
              description={error}
              style={{ paddingTop: 48 }}
            />
          ) : (
            tabs[tab]
          )}
        </div>
      </PullToRefresh>
      <TabBar activeKey={tab} onChange={setTab} safeArea className="bottom-nav">
        <TabBar.Item key="home" icon={<AppOutline />} title="Home" />
        <TabBar.Item key="team" icon={<UnorderedListOutline />} title="Team" />
        <TabBar.Item key="trades" icon={<PayCircleOutline />} title="Trades" />
        <TabBar.Item
          key="approvals"
          icon={
            pendingCount ? (
              <Badge content={pendingCount}>
                <CheckShieldOutline />
              </Badge>
            ) : (
              <CheckShieldOutline />
            )
          }
          title="Inbox"
        />
      </TabBar>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App />)
