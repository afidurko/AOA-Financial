"""Neural endpoint mesh — graph + persistent Hebbian run memory.

The brain mesh (``brain/mesh/index.yaml``) already describes the twelve-member
team, algorithms, spines, and loops. This module extends that graph with the
*runtime* endpoints the swarm actually talks to (broker, LLM, web dashboard,
notifiers, vault, companion services) and layers a persistent memory on top:

- Every node and edge carries a weight in ``[0, 1]`` (prior ``0.5``).
- ``record_run(activated, ok=...)`` reinforces the nodes (and the edges
  between co-activated nodes) that participated in a run — success pulls
  weights toward ``1.0``, failure toward ``0.0`` (Hebbian-style EMA).
- Memory persists as JSON under ``data/{env}/mesh/memory.json`` so
  completion/correctness signal compounds across loop runs and sessions.

Everything here is offline-safe: building the mesh never opens a socket.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.brain.store import BrainStore

_LEARNING_RATE = 0.2
_PRIOR_WEIGHT = 0.5
_MAX_RUNS = 200
_MEMORY_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class MeshNode:
    """One vertex — a team member, algorithm, loop, spine, repo, or endpoint."""

    id: str
    kind: str  # member | algorithm | loop | spine | repo | endpoint
    label: str
    endpoint: str = ""  # URL / host:port / path when kind == "endpoint"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "kind": self.kind, "label": self.label}
        if self.endpoint:
            out["endpoint"] = self.endpoint
        return out


@dataclass(frozen=True)
class MeshEdge:
    """One directed connection between two mesh nodes."""

    src: str
    dst: str
    relation: str  # feeds | owns | serves | notifies | persists

    @property
    def key(self) -> str:
        return f"{self.src}->{self.dst}"

    def to_dict(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "relation": self.relation}


@dataclass
class MeshMemory:
    """Persistent per-node/per-edge weights plus a bounded run history."""

    node_weights: dict[str, float] = field(default_factory=dict)
    edge_weights: dict[str, float] = field(default_factory=dict)
    runs: list[dict[str, Any]] = field(default_factory=list)

    def node_weight(self, node_id: str) -> float:
        return float(self.node_weights.get(node_id, _PRIOR_WEIGHT))

    def edge_weight(self, edge_key: str) -> float:
        return float(self.edge_weights.get(edge_key, _PRIOR_WEIGHT))

    def reinforce(
        self,
        activated: list[str],
        *,
        ok: bool,
        edges: list[MeshEdge],
        alpha: float = _LEARNING_RATE,
    ) -> None:
        target = 1.0 if ok else 0.0
        active = set(activated)
        for node_id in active:
            prev = self.node_weight(node_id)
            self.node_weights[node_id] = round(prev + alpha * (target - prev), 6)
        for edge in edges:
            if edge.src in active and edge.dst in active:
                prev = self.edge_weight(edge.key)
                self.edge_weights[edge.key] = round(prev + alpha * (target - prev), 6)

    def record(self, *, outcome: str, activated: list[str], ok: bool, note: str = "") -> None:
        self.runs.append(
            {
                "at": _utc_now(),
                "outcome": outcome,
                "ok": ok,
                "activated": sorted(set(activated)),
                "note": note,
            }
        )
        if len(self.runs) > _MAX_RUNS:
            del self.runs[: len(self.runs) - _MAX_RUNS]

    def recall(self, node_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        hits = [r for r in self.runs if node_id in (r.get("activated") or [])]
        return hits[-limit:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": _MEMORY_VERSION,
            "updated_at": _utc_now(),
            "node_weights": self.node_weights,
            "edge_weights": self.edge_weights,
            "runs": self.runs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MeshMemory:
        return cls(
            node_weights={
                str(k): float(v) for k, v in (data.get("node_weights") or {}).items()
            },
            edge_weights={
                str(k): float(v) for k, v in (data.get("edge_weights") or {}).items()
            },
            runs=[r for r in (data.get("runs") or []) if isinstance(r, dict)],
        )


class NeuralEndpointMesh:
    """Unified endpoint + brain graph with persistent run memory."""

    def __init__(
        self,
        *,
        nodes: list[MeshNode],
        edges: list[MeshEdge],
        mesh_dir: Path,
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.mesh_dir = mesh_dir
        self.memory = self._load_memory()

    # ------------------------------------------------------------------ build

    @classmethod
    def build(
        cls,
        *,
        repo_root: Path | None = None,
        cfg: Any = None,
        mesh_dir: Path | None = None,
    ) -> NeuralEndpointMesh:
        """Build the full graph from brain/mesh/index.yaml plus Config endpoints.

        ``cfg`` is optional so callers without a loaded Config (e.g. the ATTL
        controller) still get the brain-side graph and working memory.
        """
        root = repo_root or Path.cwd()
        store = BrainStore.open(root)
        nodes: dict[str, MeshNode] = {}
        edges: list[MeshEdge] = []

        def add_node(node: MeshNode) -> None:
            nodes.setdefault(node.id, node)

        def add_edge(src: str, dst: str, relation: str) -> None:
            if src in nodes and dst in nodes:
                edges.append(MeshEdge(src=src, dst=dst, relation=relation))

        # Anchor nodes referenced by member feeds outside the roster itself.
        for anchor, label in (
            ("user", "Human operator"),
            ("brain", "Second brain (brain/)"),
            ("vault", "Obsidian vault"),
            ("brief", "User brief"),
            ("factory", "Task factory"),
            ("maker", "Maker sub-agent"),
        ):
            add_node(MeshNode(id=f"anchor.{anchor}", kind="endpoint", label=label))

        for member in store.members:
            mid = str(member.get("id") or "").strip()
            if not mid:
                continue
            add_node(
                MeshNode(
                    id=f"member.{mid}",
                    kind="member",
                    label=str(member.get("name") or mid),
                )
            )
        for member in store.members:
            mid = str(member.get("id") or "").strip()
            for feed in member.get("feeds") or []:
                fid = str(feed).strip()
                if not fid:
                    continue
                if f"member.{fid}" in nodes:
                    dst = f"member.{fid}"
                elif f"anchor.{fid}" in nodes:
                    dst = f"anchor.{fid}"
                else:
                    dst = f"algorithm.{fid}" if fid.startswith("algo.") else ""
                    if dst and dst not in nodes:
                        dst = ""
                if dst:
                    add_edge(f"member.{mid}", dst, "feeds")

        for algo in store.algorithms:
            aid = str(algo.get("id") or "").strip()
            if not aid:
                continue
            add_node(MeshNode(id=f"algorithm.{aid}", kind="algorithm", label=aid))
            owner = str(algo.get("owner") or "").strip()
            if owner:
                add_edge(f"member.{owner}", f"algorithm.{aid}", "owns")

        for loop in store.mesh.get("loops") or []:
            lid = str(loop.get("id") or "").strip()
            if not lid:
                continue
            add_node(MeshNode(id=f"loop.{lid}", kind="loop", label=lid))
            for feed in loop.get("feeds") or []:
                fid = str(feed).strip()
                if f"member.{fid}" in nodes:
                    add_edge(f"loop.{lid}", f"member.{fid}", "feeds")

        for spine in store.mesh.get("spines") or []:
            path = str(spine.get("path") or "").strip()
            if not path:
                continue
            sid = f"spine.{path}"
            add_node(MeshNode(id=sid, kind="spine", label=path))
            for owner in spine.get("owners") or []:
                add_edge(f"member.{owner}", sid, "owns")

        for repo in store.repos.get("repos") or []:
            name = str(repo.get("name") or "").strip()
            if name:
                add_node(MeshNode(id=f"repo.{name}", kind="repo", label=name))

        if cfg is not None:
            cls._add_config_endpoints(cfg, add_node, add_edge)

        resolved_dir = mesh_dir or (root / "data" / "paper" / "mesh")
        return cls(nodes=list(nodes.values()), edges=edges, mesh_dir=resolved_dir)

    @staticmethod
    def _add_config_endpoints(cfg: Any, add_node, add_edge) -> None:  # noqa: ANN001
        """Attach runtime endpoints from a Config-like object to the graph."""

        def endpoint(eid: str, label: str, address: str) -> None:
            add_node(
                MeshNode(id=f"endpoint.{eid}", kind="endpoint", label=label, endpoint=address)
            )

        broker = str(getattr(cfg, "broker", "") or "")
        if broker == "moomoo":
            host = getattr(cfg, "moomoo_opend_host", "127.0.0.1")
            port = getattr(cfg, "moomoo_opend_port", 11111)
            endpoint("broker", "Moomoo OpenD", f"{host}:{port}")
        elif broker:
            endpoint("broker", "Alpaca API", "https://api.alpaca.markets")
        if broker:
            add_edge("endpoint.broker", "member.bob", "serves")
            add_edge("endpoint.broker", "member.andrea", "serves")
            add_edge("endpoint.broker", "loop.trading-swarm", "serves")

        llm_url = str(getattr(cfg, "llm_base_url", "") or "")
        if llm_url:
            endpoint("llm", "LLM provider", llm_url)
            add_edge("endpoint.llm", "loop.trading-swarm", "serves")
            add_edge("endpoint.llm", "loop.attl-mesh", "serves")

        web_host = str(getattr(cfg, "web_host", "") or "")
        if web_host:
            endpoint("web", "Web dashboard", f"{web_host}:{getattr(cfg, 'web_port', 8080)}")
            add_edge("endpoint.web", "member.alex", "serves")
            add_edge("endpoint.web", "anchor.user", "serves")

        for eid, label, attr in (
            ("ntfy", "ntfy push", "ntfy_server"),
            ("openstock", "OpenStock", "openstock_url"),
            ("qm", "Quant middleware", "qm_url"),
            ("visualhft", "VisualHFT", "visualhft_url"),
            ("vault", "Obsidian vault", "obsidian_vault_path"),
        ):
            value = str(getattr(cfg, attr, "") or "").strip()
            if value:
                endpoint(eid, label, value)
        add_edge("endpoint.ntfy", "member.aaron", "notifies")
        add_edge("endpoint.vault", "member.nova", "persists")
        add_edge("endpoint.visualhft", "member.morgan", "serves")

    # ----------------------------------------------------------- memory + I/O

    @property
    def memory_path(self) -> Path:
        return self.mesh_dir / "memory.json"

    @property
    def graph_path(self) -> Path:
        return self.mesh_dir / "graph.json"

    def _load_memory(self) -> MeshMemory:
        if not self.memory_path.is_file():
            return MeshMemory()
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return MeshMemory()
        return MeshMemory.from_dict(data if isinstance(data, dict) else {})

    def save(self) -> None:
        self.mesh_dir.mkdir(parents=True, exist_ok=True)
        self.memory_path.write_text(
            json.dumps(self.memory.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.graph_path.write_text(
            json.dumps(
                {
                    "updated_at": _utc_now(),
                    "nodes": [n.to_dict() for n in self.nodes],
                    "edges": [e.to_dict() for e in self.edges],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def record_run(
        self,
        *,
        outcome: str,
        activated: list[str],
        ok: bool,
        note: str = "",
        save: bool = True,
    ) -> None:
        """Record one loop run: reinforce weights, append history, persist."""
        known = {n.id for n in self.nodes}
        active = [a for a in activated if a in known]
        self.memory.reinforce(active, ok=ok, edges=self.edges)
        self.memory.record(outcome=outcome, activated=active, ok=ok, note=note)
        if save:
            self.save()

    # ---------------------------------------------------------------- queries

    def recall(self, node_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self.memory.recall(node_id, limit=limit)

    def weakest_nodes(self, *, limit: int = 5) -> list[tuple[str, float]]:
        """Nodes with the lowest learned weight — where correctness is eroding."""
        scored = [
            (n.id, self.memory.node_weight(n.id))
            for n in self.nodes
            if n.id in self.memory.node_weights
        ]
        scored.sort(key=lambda pair: pair[1])
        return scored[:limit]

    def health(self) -> float:
        """Mean learned node weight in [0, 1]; 0.5 when nothing is learned yet."""
        if not self.memory.node_weights:
            return _PRIOR_WEIGHT
        values = list(self.memory.node_weights.values())
        return round(sum(values) / len(values), 4)

    def stats(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for node in self.nodes:
            kinds[node.kind] = kinds.get(node.kind, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "kinds": dict(sorted(kinds.items())),
            "learned_nodes": len(self.memory.node_weights),
            "learned_edges": len(self.memory.edge_weights),
            "runs_remembered": len(self.memory.runs),
            "health": self.health(),
            "weakest": self.weakest_nodes(),
            "memory_path": str(self.memory_path),
        }
