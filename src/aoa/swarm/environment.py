"""Cohesive, editable swarm environment.

Each cycle builds a :class:`SwarmEnvironment` that meshes specialist outputs
into one auditable workspace.  The environment can be edited at two levels:

- **Global** — cycle-wide context (account snapshot, commentary, overrides).
- **Domain** — per-agent slices (technical, fundamental, scanner, …) that
  retain their own data and can be patched independently.
- **Meshed** — unified per-symbol views produced by the meshing agent, also
  editable without touching the underlying domain slices.

Downstream agents (options strategist, portfolio manager) read the *effective*
meshed view — base synthesis plus any overrides — so human or programmatic edits
propagate without re-running the full pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aoa.agents.base import Direction, Signal


@dataclass
class DomainSlice:
    """One specialist's slice of the cycle environment."""

    domain: str
    data: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)

    def edit(self, **updates: Any) -> None:
        """Apply domain-specific overrides without mutating the base data."""
        self.overrides.update(updates)

    def clear_overrides(self) -> None:
        self.overrides.clear()

    def effective(self) -> dict[str, Any]:
        merged = dict(self.data)
        merged.update(self.overrides)
        return merged

    def to_context(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "data": self.data,
            "overrides": self.overrides,
            "effective": self.effective(),
        }


@dataclass
class MeshedView:
    """Unified per-symbol synthesis from the meshing agent."""

    symbol: str
    direction: Direction
    conviction: float
    rationale: str
    horizon: str = "swing"
    conflicts: list[str] = field(default_factory=list)
    corroboration: str = "mixed"  # "strong" | "mixed" | "weak" | "none"
    source_signals: list[dict] = field(default_factory=list)
    key_levels: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    overrides: dict[str, Any] = field(default_factory=dict)

    def edit(self, **updates: Any) -> None:
        """Patch the meshed view without altering underlying domain slices."""
        self.overrides.update(updates)

    def clear_overrides(self) -> None:
        self.overrides.clear()

    @property
    def effective_direction(self) -> Direction:
        raw = self.overrides.get("direction", self.direction.value)
        return Direction(raw) if isinstance(raw, str) else raw

    @property
    def effective_conviction(self) -> float:
        raw = self.overrides.get("conviction", self.conviction)
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return self.conviction

    @property
    def effective_rationale(self) -> str:
        return str(self.overrides.get("rationale", self.rationale))

    @property
    def effective_horizon(self) -> str:
        return str(self.overrides.get("horizon", self.horizon))

    def to_signal(self) -> Signal:
        """Convert the effective meshed view into a canonical :class:`Signal`."""
        return Signal(
            symbol=self.symbol,
            source="meshing",
            direction=self.effective_direction,
            conviction=self.effective_conviction,
            rationale=self.effective_rationale,
            horizon=self.effective_horizon,
            key_levels=dict(self.key_levels),
            tags=["meshed", *self.tags],
        )

    def to_context(self) -> dict[str, Any]:
        sig = self.to_signal()
        return {
            **sig.to_context(),
            "conflicts": self.conflicts,
            "corroboration": self.corroboration,
            "source_signals": self.source_signals,
            "overrides": self.overrides,
            "has_overrides": bool(self.overrides),
        }


@dataclass
class SwarmEnvironment:
    """Cohesive per-cycle workspace connecting all specialist domains."""

    global_context: dict[str, Any] = field(default_factory=dict)
    global_overrides: dict[str, Any] = field(default_factory=dict)
    domains: dict[str, DomainSlice] = field(default_factory=dict)
    meshed_views: dict[str, MeshedView] = field(default_factory=dict)
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)

    def ensure_domain(self, domain: str) -> DomainSlice:
        if domain not in self.domains:
            self.domains[domain] = DomainSlice(domain=domain)
        return self.domains[domain]

    def set_domain(self, domain: str, data: dict[str, Any]) -> DomainSlice:
        slice_ = self.ensure_domain(domain)
        slice_.data = dict(data)
        return slice_

    def edit_domain(self, domain: str, **updates: Any) -> DomainSlice:
        slice_ = self.ensure_domain(domain)
        slice_.edit(**updates)
        return slice_

    def edit_global(self, **updates: Any) -> None:
        self.global_overrides.update(updates)

    def edit_meshed(self, symbol: str, **updates: Any) -> MeshedView | None:
        view = self.meshed_views.get(symbol.upper())
        if view is None:
            return None
        view.edit(**updates)
        return view

    def set_meshed(self, view: MeshedView) -> None:
        self.meshed_views[view.symbol.upper()] = view

    def checkpoint(self, stage: str) -> None:
        """Snapshot editable state after a pipeline stage completes."""
        self.checkpoints[stage] = {
            "global_context": dict(self.global_context),
            "global_overrides": dict(self.global_overrides),
            "domains": {
                name: {"data": dict(s.data), "overrides": dict(s.overrides)}
                for name, s in self.domains.items()
            },
            "meshed_views": {
                sym: {
                    "direction": v.direction.value,
                    "conviction": v.conviction,
                    "rationale": v.rationale,
                    "horizon": v.horizon,
                    "conflicts": list(v.conflicts),
                    "corroboration": v.corroboration,
                    "overrides": dict(v.overrides),
                }
                for sym, v in self.meshed_views.items()
            },
        }

    def list_checkpoints(self) -> list[str]:
        return list(self.checkpoints.keys())

    def effective_global(self) -> dict[str, Any]:
        merged = dict(self.global_context)
        merged.update(self.global_overrides)
        return merged

    def per_symbol_context(self) -> list[dict[str, Any]]:
        """Context bundle for the portfolio manager — one entry per meshed symbol."""
        rows: list[dict[str, Any]] = []
        for symbol, view in sorted(self.meshed_views.items()):
            scanner = self.domains.get("scanner")
            scanner_ctx = {}
            if scanner:
                by_symbol = scanner.effective().get("by_symbol", {})
                scanner_ctx = by_symbol.get(symbol, {})

            options_slice = self.domains.get(f"options:{symbol}")
            options_idea = options_slice.effective() if options_slice else None

            row: dict[str, Any] = {
                "symbol": symbol,
                "scanner_reason": scanner_ctx.get("reason", ""),
                "meshed_view": view.to_context(),
                "domains": {
                    name: slice_.effective()
                    for name, slice_ in self.domains.items()
                    if name.endswith(f":{symbol}") or name == "scanner"
                },
            }
            research = self.domains.get(f"research:{symbol}")
            if research:
                row["research_debate"] = research.effective()
            if options_idea:
                row["options_idea"] = {
                    k: v for k, v in options_idea.items() if not str(k).startswith("_")
                }
            rows.append(row)
        return rows

    def to_context(self) -> dict[str, Any]:
        return {
            "global": self.effective_global(),
            "global_overrides": self.global_overrides,
            "domains": {name: s.to_context() for name, s in self.domains.items()},
            "meshed_views": {sym: v.to_context() for sym, v in self.meshed_views.items()},
            "checkpoints": list(self.checkpoints.keys()),
        }
