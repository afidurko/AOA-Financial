"""Tests for the neural endpoint mesh — graph build, memory, persistence."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from aoa.cli import cmd_mesh_recall, cmd_mesh_status, cmd_mesh_sync
from aoa.config import Config
from aoa.mesh.graph import MeshEdge, MeshMemory, NeuralEndpointMesh


def test_build_from_repo_brain_with_config(tmp_path: Path):
    cfg = Config(broker="moomoo", web_host="127.0.0.1", web_port=8080)
    mesh = NeuralEndpointMesh.build(repo_root=Path.cwd(), cfg=cfg, mesh_dir=tmp_path)

    node_ids = {n.id for n in mesh.nodes}
    assert {"member.nova", "member.reed", "member.kai"} <= node_ids
    assert "endpoint.broker" in node_ids
    assert "endpoint.llm" in node_ids
    assert "endpoint.web" in node_ids
    assert "loop.attl-mesh" in node_ids
    assert any(n.kind == "algorithm" for n in mesh.nodes)
    assert any(n.kind == "spine" for n in mesh.nodes)

    edge_keys = {e.key for e in mesh.edges}
    assert "endpoint.broker->member.bob" in edge_keys
    assert "member.nova->anchor.brain" in edge_keys

    stats = mesh.stats()
    assert stats["nodes"] == len(node_ids)
    assert stats["health"] == 0.5  # nothing learned yet


def test_build_without_config_is_brain_only(tmp_path: Path):
    mesh = NeuralEndpointMesh.build(repo_root=Path.cwd(), mesh_dir=tmp_path)
    node_ids = {n.id for n in mesh.nodes}
    assert "member.nova" in node_ids
    assert "endpoint.broker" not in node_ids


def test_memory_reinforcement_and_recall():
    memory = MeshMemory()
    edges = [MeshEdge(src="member.nova", dst="member.reed", relation="feeds")]

    memory.reinforce(["member.nova", "member.reed"], ok=True, edges=edges)
    assert memory.node_weight("member.nova") > 0.5
    assert memory.edge_weight("member.nova->member.reed") > 0.5

    memory.reinforce(["member.nova"], ok=False, edges=edges)
    assert memory.node_weight("member.nova") < memory.node_weight("member.reed")
    # Edge untouched on second pass — reed was not co-activated.
    assert memory.edge_weight("member.nova->member.reed") > 0.5

    memory.record(outcome="auto-continue", activated=["member.nova"], ok=True)
    memory.record(outcome="paused", activated=["member.kai"], ok=False)
    hits = memory.recall("member.nova")
    assert len(hits) == 1
    assert hits[0]["outcome"] == "auto-continue"


def test_run_history_is_bounded():
    memory = MeshMemory()
    for i in range(250):
        memory.record(outcome=f"run-{i}", activated=["member.nova"], ok=True)
    assert len(memory.runs) == 200
    assert memory.runs[-1]["outcome"] == "run-249"
    assert memory.runs[0]["outcome"] == "run-50"


def test_record_run_persists_and_reloads(tmp_path: Path):
    mesh = NeuralEndpointMesh.build(repo_root=Path.cwd(), mesh_dir=tmp_path)
    mesh.record_run(
        outcome="auto-continue",
        activated=["member.nova", "member.reed", "not-a-node"],
        ok=True,
        note="test",
    )
    assert mesh.memory_path.is_file()
    assert mesh.graph_path.is_file()

    reloaded = NeuralEndpointMesh.build(repo_root=Path.cwd(), mesh_dir=tmp_path)
    assert reloaded.memory.node_weight("member.nova") > 0.5
    # Unknown node ids are dropped, never learned.
    assert "not-a-node" not in reloaded.memory.node_weights
    hits = reloaded.recall("member.reed")
    assert len(hits) == 1
    assert hits[0]["note"] == "test"
    assert reloaded.health() > 0.5

    graph = json.loads(mesh.graph_path.read_text(encoding="utf-8"))
    assert {"nodes", "edges", "updated_at"} <= set(graph)


def test_failure_lowers_health_and_surfaces_weak_nodes(tmp_path: Path):
    mesh = NeuralEndpointMesh.build(repo_root=Path.cwd(), mesh_dir=tmp_path)
    for _ in range(3):
        mesh.record_run(outcome="critical-report", activated=["member.kai"], ok=False)
    assert mesh.health() < 0.5
    weakest = mesh.weakest_nodes(limit=1)
    assert weakest[0][0] == "member.kai"
    assert weakest[0][1] < 0.5


def test_attl_controller_feeds_mesh_memory(tmp_path: Path):
    from aoa.attl.mesh import MeshController

    _seed_repo(tmp_path)
    ctrl = MeshController(repo_root=tmp_path, data_dir=tmp_path / "data" / "attl")
    snap = ctrl.sync(dry_run=True, bob_can_proceed=True, create_worktree=False)
    assert snap.outcome == "dry-run"

    memory_path = tmp_path / "data" / "mesh" / "memory.json"
    assert memory_path.is_file()
    data = json.loads(memory_path.read_text(encoding="utf-8"))
    assert data["runs"], "ATTL run must be remembered"
    assert data["runs"][-1]["ok"] is True
    assert "member.nova" in data["runs"][-1]["activated"]
    assert data["node_weights"]["member.reed"] > 0.5


def test_cli_mesh_commands(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("AOA_DATA_DIR", str(tmp_path))
    cfg = Config(broker="moomoo")

    assert cmd_mesh_sync(cfg) == 0
    out = capsys.readouterr().out
    assert "Mesh synced" in out
    assert (tmp_path / "paper-dry" / "mesh" / "graph.json").is_file()

    assert cmd_mesh_status(cfg) == 0
    out = capsys.readouterr().out
    assert "Neural endpoint mesh" in out
    assert "health" in out

    assert cmd_mesh_status(cfg, as_json=True) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["nodes"] > 0
    assert stats["edges"] > 0

    assert cmd_mesh_recall(cfg, "member.nova") == 0
    out = capsys.readouterr().out
    assert "No remembered runs" in out

    mesh = NeuralEndpointMesh.build(
        repo_root=Path.cwd(), cfg=cfg, mesh_dir=tmp_path / "paper-dry" / "mesh"
    )
    mesh.record_run(outcome="auto-continue", activated=["member.nova"], ok=True)
    assert cmd_mesh_recall(cfg, "member.nova") == 0
    out = capsys.readouterr().out
    assert "auto-continue" in out


def _seed_repo(root: Path) -> None:
    from aoa.team.roster import TWELVE_MEMBER_ROSTER

    (root / "STATE.md").write_text(
        "## Loop automation\n\n- L1: enabled\n- L2: enabled\n", encoding="utf-8"
    )
    (root / "loop-run-log.md").write_text(
        "| Timestamp (UTC) | Loop | Level | Outcome | Notes |\n|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    (root / "loop-constraints.md").write_text(
        Path.cwd().joinpath("loop-constraints.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    mesh = {
        "version": 1,
        "mode": "auto-12",
        "members": [
            {"id": m.slug, "name": m.name, "role": m.role, "feeds": []}
            for m in TWELVE_MEMBER_ROSTER
        ],
        "algorithms": [{"id": "algo.julie", "owner": "julie"}],
        "spines": [],
        "loops": [{"id": "attl-mesh", "feeds": []}],
    }
    for rel in (
        "_CLAUDE.md",
        "README.md",
        "spine/ATTL.md",
        "spine/Algorithms.md",
        "spine/Team-Mesh.md",
    ):
        path = root / "brain" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")
    (root / "brain" / "captures").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "decisions").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "mesh").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "mesh" / "index.yaml").write_text(yaml.safe_dump(mesh), encoding="utf-8")
    (root / "brain" / "mesh" / "repos.yaml").write_text(
        yaml.safe_dump({"repos": []}), encoding="utf-8"
    )
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "upgrade-backlog.json").write_text(
        json.dumps(
            {
                "items": {
                    "upg-x": {
                        "title": "Test item",
                        "automatable": True,
                        "skill": "minimal-fix",
                        "detail": "x",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
