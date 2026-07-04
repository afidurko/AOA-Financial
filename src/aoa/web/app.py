"""FastAPI application — REST API + embedded dashboard."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from aoa.analytics.bridge import _analyst_reports_from_env
from aoa.analytics.store import AnalyticsStore
from aoa.brokerage.base import BrokerError
from aoa.cli import build_team
from aoa.config import Config
from aoa.llm.client import LLMError
from aoa.research.loop import ResearchLoop
from aoa.team.orchestrator import TeamCycleResult
from aoa.web.dashboard_html import DASHBOARD_HTML
from aoa.web.loop_runner import CycleBusyError, LoopRunner


class ResolveBody(BaseModel):
    status: str


class TeamExpansionUpdateBody(BaseModel):
    promotion_title: str | None = None
    team_name: str | None = None
    mission: str | None = None
    expansion_rationale: str | None = None
    first_quarter_goals: list[str] | None = None
    members: list[dict[str, Any]] | None = None


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config.from_env()
    team = build_team(cfg)
    runner = LoopRunner(team, cfg.cycle_seconds)
    analytics_store = team.analytics.store if team.analytics else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.cfg = cfg
        app.state.team = team
        app.state.runner = runner
        app.state.analytics_store = analytics_store
        if cfg.web_auto_loop:
            runner.start()
        yield
        runner.stop()

    app = FastAPI(
        title="AOA Financial",
        version="0.2.0",
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
            "cycle_seconds_market_open": cfg.cycle_seconds_market_open,
            "cycle_seconds_market_closed": cfg.cycle_seconds_market_closed,
            "universe": list(cfg.universe),
            "news_enabled": cfg.news_enabled,
            "team_mode": True,
            "team_parallel": cfg.team_parallel,
            "team_subagents_enabled": cfg.team_subagents_enabled,
            "analytics_enabled": cfg.analytics_enabled,
            "scholar_enabled": cfg.scholar_enabled,
            "loop_running": runner.state.running,
            "opportunity_sweep_enabled": cfg.opportunity_sweep_enabled,
            "opportunity_sweep_seconds": cfg.opportunity_sweep_seconds,
            "openstock_url": cfg.openstock_url,
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
            "opportunity_sweep": _sweep_state_dict(runner.sweep_state()),
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

    @app.get("/api/opportunity-sweep")
    def opportunity_sweep_status(request: Request) -> dict[str, Any]:
        runner = request.app.state.runner
        return {"sweep": _sweep_state_dict(runner.sweep_state())}

    @app.post("/api/opportunity-sweep/run")
    def opportunity_sweep_run(request: Request) -> dict[str, Any]:
        runner = request.app.state.runner
        try:
            result = runner.run_sweep_once()
        except CycleBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (BrokerError, LLMError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "trends": len(result.trends),
            "catalysts": len(result.catalysts),
            "opportunities_notified": result.opportunities_notified,
            "summary": result.decision.summary if result.decision else "",
        }

    @app.get("/api/last-cycle")
    def last_cycle(request: Request) -> dict[str, Any]:
        runner = request.app.state.runner
        if runner.state.last_result is None:
            return {"result": None}
        return {"result": _team_cycle_to_dict(runner.state.last_result)}

    @app.get("/api/analytics/last-cycle")
    def analytics_last_cycle(request: Request) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        row = store.get_last_cycle()
        return {"cycle": row}

    @app.get("/api/analytics/roi")
    def analytics_roi(request: Request) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            return {"cycles_recorded": 0, "halt_rate": 0.0, "approved_proposals": 0}
        return store.roi_summary()

    @app.get("/api/approvals")
    def list_approvals(request: Request, status: str | None = None) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            return {"items": []}
        return {"items": store.list_approvals(status=status)}

    @app.post("/api/approvals/{approval_id}/resolve")
    def resolve_approval(
        request: Request, approval_id: str, body: ResolveBody
    ) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        if body.status not in {"approved", "rejected", "deferred"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        ok = store.resolve_approval(approval_id, body.status)
        if not ok:
            raise HTTPException(status_code=404, detail="Approval not found")
        return {"id": approval_id, "status": body.status}

    @app.get("/api/research/proposals")
    def list_research(request: Request, status: str | None = None) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            return {"items": []}
        return {"items": store.list_research_proposals(status=status)}

    @app.post("/api/research/discover")
    def research_discover(request: Request) -> dict[str, Any]:
        cfg: Config = request.app.state.cfg
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        loop = ResearchLoop(cfg, store)
        created = loop.run_discover()
        return {"created": created}

    @app.post("/api/research/{proposal_id}/resolve")
    def resolve_research(
        request: Request, proposal_id: str, body: ResolveBody
    ) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        if body.status not in {"approved", "rejected"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        ok = store.resolve_research_proposal(proposal_id, body.status)
        if not ok:
            raise HTTPException(status_code=404, detail="Proposal not found")
        return {"id": proposal_id, "status": body.status}

    @app.get("/api/assistant/brief")
    def assistant_brief(request: Request) -> dict[str, Any]:
        team = request.app.state.team
        runner = request.app.state.runner
        brief = team.run_assistant_brief(last_cycle=runner.state.last_result)
        return {"brief": brief.to_context()}

    @app.get("/api/team/expansions")
    def list_team_expansions(request: Request, status: str | None = None) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            return {"items": []}
        return {"items": store.list_team_expansions(status=status)}

    @app.post("/api/team/expansions/propose")
    def propose_team_expansions(request: Request) -> dict[str, Any]:
        team = request.app.state.team
        if team.analytics is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        try:
            proposals = team.propose_team_expansions()
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"proposals": [p.to_context() for p in proposals]}

    @app.get("/api/team/expansions/{expansion_id}")
    def get_team_expansion(request: Request, expansion_id: str) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        row = store.get_team_expansion(expansion_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Proposal not found")
        return {"proposal": row}

    @app.patch("/api/team/expansions/{expansion_id}")
    def update_team_expansion(
        request: Request, expansion_id: str, body: TeamExpansionUpdateBody
    ) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        ok = store.update_team_expansion(
            expansion_id,
            promotion_title=body.promotion_title,
            team_name=body.team_name,
            mission=body.mission,
            expansion_rationale=body.expansion_rationale,
            first_quarter_goals=body.first_quarter_goals,
            members=body.members,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Proposal not found or not pending")
        row = store.get_team_expansion(expansion_id)
        return {"proposal": row}

    @app.post("/api/team/expansions/{expansion_id}/resolve")
    def resolve_team_expansion(
        request: Request, expansion_id: str, body: ResolveBody
    ) -> dict[str, Any]:
        store: AnalyticsStore | None = request.app.state.analytics_store
        if store is None:
            raise HTTPException(status_code=404, detail="Analytics disabled")
        if body.status not in {"approved", "rejected"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        ok = store.resolve_team_expansion(expansion_id, body.status)
        if not ok:
            raise HTTPException(status_code=404, detail="Proposal not found")
        return {"id": expansion_id, "status": body.status}

    @app.get("/api/events/stream")
    async def events_stream(request: Request) -> StreamingResponse:
        runner: LoopRunner = request.app.state.runner

        async def generate():
            last_at = runner.state.last_cycle_at
            while True:
                if await request.is_disconnected():
                    break
                cur = runner.state.last_cycle_at
                if cur != last_at:
                    last_at = cur
                    payload = {"event": "cycle.complete", "at": cur}
                    yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return DASHBOARD_HTML

    return app


def _sweep_state_dict(state) -> dict[str, Any]:
    return {
        "enabled": state.enabled,
        "idle_seconds": round(state.idle_seconds, 1),
        "threshold_seconds": state.threshold_seconds,
        "seconds_until_sweep": max(0.0, round(state.threshold_seconds - state.idle_seconds, 1)),
        "last_activity_at": state.last_activity_at,
        "last_sweep_at": state.last_sweep_at,
        "sweeps_completed": state.sweeps_completed,
        "last_opportunities_found": state.last_opportunities_found,
        "last_error": state.last_error,
        "sweep_running": state.sweep_running,
    }


def _team_cycle_to_dict(result: TeamCycleResult) -> dict[str, Any]:
    out: dict[str, Any] = {
        "halted": result.halted,
        "halt_reason": result.halt_reason,
        "health": result.health.to_context() if result.health else None,
        "trends": [t.to_context() for t in result.trends],
        "algorithms": [a.to_context() for a in result.algorithms],
        "market_contexts": [m.to_context() for m in result.market_contexts],
        "catalysts": [c.to_context() for c in result.catalysts],
        "risk_plans": [r.to_context() for r in result.risk_plans],
        "decision": result.decision.to_context() if result.decision else None,
        "ceo": result.ceo.to_context() if result.ceo else None,
        "assistant": result.assistant.to_context() if result.assistant else None,
        "team_status": result.ceo.team_status if result.ceo else [],
        "notes": [],
        "commentary": "",
        "candidates": [],
        "proposals": [],
        "analyst_reports": [],
        "execution": None,
        "stage_metrics": [],
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
            "analyst_reports": _analyst_reports_from_env(bb.environment),
        }
    )
    return out
