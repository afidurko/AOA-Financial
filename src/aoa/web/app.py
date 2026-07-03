"""FastAPI application — REST API + embedded dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from aoa.brokerage.base import BrokerError
from aoa.cli import build_team
from aoa.config import Config
from aoa.llm.client import LLMError
from aoa.team.orchestrator import TeamCycleResult
from aoa.web.loop_runner import CycleBusyError, LoopRunner


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config.from_env()
    team = build_team(cfg)
    runner = LoopRunner(team, cfg.cycle_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.cfg = cfg
        app.state.team = team
        app.state.runner = runner
        if cfg.web_auto_loop:
            runner.start()
        yield
        runner.stop()

    app = FastAPI(
        title="AOA Financial",
        version="0.1.0",
        docs_url="/api/docs",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    def api_config(request: Request) -> dict[str, Any]:
        cfg = request.app.state.cfg
        runner = request.app.state.runner
        return {
            "trading_mode": cfg.trading_mode,
            "dry_run": cfg.dry_run,
            "cycle_seconds": cfg.cycle_seconds,
            "universe": list(cfg.universe),
            "news_enabled": cfg.news_enabled,
            "team_mode": True,
            "loop_running": runner.state.running,
        }

    @app.get("/api/status")
    def api_status(request: Request) -> dict[str, Any]:
        cfg = request.app.state.cfg
        runner = request.app.state.runner
        try:
            acct = runner.broker.get_account()
            positions = runner.broker.get_positions()
        except BrokerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "mode": cfg.trading_mode,
            "broker": runner.broker.name,
            "market_open": runner.broker.is_market_open(),
            "account": acct.to_context(),
            "positions": [p.to_context() for p in positions],
            "loop": {
                "running": runner.state.running,
                "cycles_completed": runner.state.cycles_completed,
                "last_cycle_at": runner.state.last_cycle_at,
                "last_error": runner.state.last_error,
            },
        }

    @app.get("/api/journal")
    def api_journal(request: Request, n: int = 30) -> dict[str, Any]:
        runner = request.app.state.runner
        return {"entries": runner.journal.tail(n)}

    @app.post("/api/run")
    def api_run(request: Request) -> dict[str, Any]:
        runner = request.app.state.runner
        try:
            result = runner.run_once()
        except CycleBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (BrokerError, LLMError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _team_cycle_to_dict(result)

    @app.post("/api/loop/start")
    def loop_start(request: Request) -> dict[str, str]:
        request.app.state.runner.start()
        return {"status": "started"}

    @app.post("/api/loop/stop")
    def loop_stop(request: Request) -> dict[str, str]:
        request.app.state.runner.stop()
        return {"status": "stopped"}

    @app.get("/api/last-cycle")
    def last_cycle(request: Request) -> dict[str, Any]:
        runner = request.app.state.runner
        if runner.state.last_result is None:
            return {"result": None}
        return {"result": _team_cycle_to_dict(runner.state.last_result)}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return _DASHBOARD_HTML

    return app


def _team_cycle_to_dict(result: TeamCycleResult) -> dict[str, Any]:
    out: dict[str, Any] = {
        "halted": result.halted,
        "halt_reason": result.halt_reason,
        "health": result.health.to_context() if result.health else None,
        "trends": [t.to_context() for t in result.trends],
        "algorithms": [a.to_context() for a in result.algorithms],
        "decision": result.decision.to_context() if result.decision else None,
        "ceo": result.ceo.to_context() if result.ceo else None,
        "notes": [],
        "commentary": "",
        "candidates": [],
        "proposals": [],
        "execution": None,
    }
    if result.cycle is None:
        return out
    cycle = result.cycle
    bb = cycle.blackboard
    proposals = [p.to_context() for p in bb.proposals]
    execution = None
    if cycle.execution:
        execution = {
            "dry_run": cycle.execution.dry_run,
            "submitted": len(cycle.execution.submitted),
            "skipped": len(cycle.execution.skipped),
            "errors": cycle.execution.errors,
        }
    out.update(
        {
            "notes": cycle.notes,
            "commentary": bb.commentary,
            "candidates": bb.candidates,
            "proposals": proposals,
            "execution": execution,
        }
    )
    return out


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AOA Financial</title>
  <style>
    :root {
      --bg: #0f1419; --surface: #1a2332; --border: #2d3a4f;
      --text: #e7ecf3; --muted: #8b9cb3; --accent: #3b82f6;
      --green: #22c55e; --red: #ef4444; --amber: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.5; min-height: 100vh;
    }
    header {
      padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;
    }
    h1 { font-size: 1.25rem; font-weight: 600; }
    .badge {
      display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px;
      font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    }
    .badge-paper { background: #1e3a5f; color: #93c5fd; }
    .badge-live { background: #450a0a; color: #fca5a5; }
    .badge-dry { background: #422006; color: #fcd34d; }
    main { padding: 1.5rem; max-width: 1200px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
    .card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem;
    }
    .card h2 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 0.75rem; }
    .stat { font-size: 1.5rem; font-weight: 700; }
    .stat-sm { font-size: 0.9rem; color: var(--muted); margin-top: 0.25rem; }
    .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
    button {
      background: var(--accent); color: white; border: none; border-radius: 8px;
      padding: 0.55rem 1rem; font-size: 0.875rem; font-weight: 600; cursor: pointer;
    }
    button:hover { filter: brightness(1.1); }
    button.secondary { background: var(--surface); border: 1px solid var(--border); color: var(--text); }
    button.danger { background: var(--red); }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; }
    .approved { color: var(--green); }
    .blocked { color: var(--red); }
    .journal-entry { font-family: ui-monospace, monospace; font-size: 0.8rem; padding: 0.35rem 0; border-bottom: 1px solid var(--border); }
    .journal-ts { color: var(--muted); margin-right: 0.5rem; }
    #toast {
      position: fixed; bottom: 1.5rem; right: 1.5rem; background: var(--surface);
      border: 1px solid var(--border); padding: 0.75rem 1rem; border-radius: 8px;
      display: none; max-width: 360px; font-size: 0.875rem;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AOA Financial</h1>
      <span id="mode-badge" class="badge badge-paper">loading</span>
    </div>
    <div id="market-status" class="stat-sm">Market: —</div>
  </header>
  <main>
    <div class="actions">
      <button onclick="runCycle()">Run cycle</button>
      <button class="secondary" onclick="startLoop()">Start loop</button>
      <button class="secondary danger" onclick="stopLoop()">Stop loop</button>
      <button class="secondary" onclick="refresh()">Refresh</button>
    </div>
    <div class="grid">
      <div class="card"><h2>Equity</h2><div class="stat" id="equity">—</div></div>
      <div class="card"><h2>Settled cash</h2><div class="stat" id="cash">—</div></div>
      <div class="card"><h2>Positions</h2><div class="stat" id="pos-count">—</div></div>
      <div class="card"><h2>Loop</h2><div class="stat" id="loop-status">—</div><div class="stat-sm" id="loop-detail"></div></div>
    </div>
    <div class="grid">
      <div class="card" style="grid-column: 1 / -1;">
        <h2>Positions</h2>
        <table><thead><tr><th>Symbol</th><th>Class</th><th>Qty</th><th>MV</th><th>uPL</th></tr></thead>
        <tbody id="positions-body"><tr><td colspan="5">Loading…</td></tr></tbody></table>
      </div>
    </div>
    <div class="grid">
      <div class="card" style="grid-column: 1 / -1;">
        <h2>Team (Bob → Tom → Julie → Alan → Aaron)</h2>
        <div class="stat-sm" id="team-health">Health: —</div>
        <div class="stat-sm" id="team-ceo" style="margin-top:0.5rem">CEO: —</div>
        <div class="stat-sm" id="team-alerts" style="margin-top:0.5rem;color:var(--amber)"></div>
      </div>
    </div>
    <div class="grid">
      <div class="card" style="grid-column: 1 / -1;">
        <h2>Last cycle proposals</h2>
        <table><thead><tr><th>Status</th><th>Side</th><th>Qty</th><th>Symbol</th><th>Strategy</th><th>Notional</th></tr></thead>
        <tbody id="proposals-body"><tr><td colspan="6">No cycle run yet</td></tr></tbody></table>
      </div>
    </div>
    <div class="card">
      <h2>Journal (recent)</h2>
      <div id="journal"></div>
    </div>
  </main>
  <div id="toast"></div>
  <script>
    const fmt = (n) => n == null ? '—' : '$' + Number(n).toLocaleString(undefined, {maximumFractionDigits: 0});
    const toast = (msg) => {
      const el = document.getElementById('toast');
      el.textContent = msg; el.style.display = 'block';
      setTimeout(() => el.style.display = 'none', 4000);
    };
    async function refresh() {
      const [status, last, journal] = await Promise.all([
        fetch('/api/status').then(r => r.json()),
        fetch('/api/last-cycle').then(r => r.json()),
        fetch('/api/journal?n=15').then(r => r.json()),
      ]);
      const badge = document.getElementById('mode-badge');
      badge.textContent = status.mode;
      badge.className = 'badge ' + (status.mode === 'live' ? 'badge-live' : status.mode === 'dry-run' ? 'badge-dry' : 'badge-paper');
      document.getElementById('market-status').textContent = 'Market: ' + (status.market_open ? 'OPEN' : 'CLOSED') + ' · ' + status.broker;
      document.getElementById('equity').textContent = fmt(status.account.equity);
      document.getElementById('cash').textContent = fmt(status.account.settled_cash);
      document.getElementById('pos-count').textContent = status.positions.length;
      document.getElementById('loop-status').textContent = status.loop.running ? 'Running' : 'Stopped';
      document.getElementById('loop-detail').textContent = status.loop.last_cycle_at
        ? 'Last: ' + status.loop.last_cycle_at + ' (' + status.loop.cycles_completed + ' total)'
        : (status.loop.last_error || '');
      const pb = document.getElementById('positions-body');
      pb.innerHTML = status.positions.length
        ? status.positions.map(p => `<tr><td>${p.symbol}</td><td>${p.asset_class}</td><td>${p.qty}</td><td>${fmt(p.market_value)}</td><td>${fmt(p.unrealized_pl)}</td></tr>`).join('')
        : '<tr><td colspan="5">No open positions</td></tr>';
      const proposals = last.result?.proposals || [];
      document.getElementById('proposals-body').innerHTML = proposals.length
        ? proposals.map(p => `<tr><td class="${p.approved ? 'approved' : 'blocked'}">${p.approved ? 'APPROVED' : 'blocked'}</td><td>${p.side}</td><td>${p.qty}</td><td>${p.symbol}</td><td>${p.strategy}</td><td>${fmt(p.est_notional)}</td></tr>`).join('')
        : '<tr><td colspan="6">No proposals</td></tr>';
      const team = last.result || {};
      document.getElementById('team-health').textContent = team.health
        ? `Health: ${team.health.summary} (${team.health.worst_status})`
        : 'Health: —';
      document.getElementById('team-ceo').textContent = team.ceo
        ? `Aaron: ${team.ceo.summary}`
        : 'CEO: —';
      const alerts = (team.ceo?.user_notifications || []).concat(team.halted ? [team.halt_reason] : []);
      document.getElementById('team-alerts').textContent = alerts.length
        ? '⚠ ' + alerts.join(' · ')
        : '';
      document.getElementById('journal').innerHTML = (journal.entries || []).slice().reverse().map(e =>
        `<div class="journal-entry"><span class="journal-ts">${e.ts || ''}</span>${e.event || ''}</div>`
      ).join('') || 'Empty';
    }
    async function runCycle() {
      toast('Running cycle…');
      const r = await fetch('/api/run', {method: 'POST'});
      if (!r.ok) { toast('Cycle failed: ' + (await r.json()).detail); return; }
      toast('Cycle complete');
      refresh();
    }
    async function startLoop() {
      await fetch('/api/loop/start', {method: 'POST'});
      toast('Loop started'); refresh();
    }
    async function stopLoop() {
      await fetch('/api/loop/stop', {method: 'POST'});
      toast('Loop stopped'); refresh();
    }
    refresh();
    setInterval(refresh, 30000);
  </script>
</body>
</html>"""
