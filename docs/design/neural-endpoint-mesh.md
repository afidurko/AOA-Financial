# Neural Endpoint Mesh

One weighted graph over everything the swarm touches, with persistent memory
of every loop run so completion and correctness compound across sessions.

## What it meshes

| Layer | Nodes | Source |
|-------|-------|--------|
| Team | `member.*` (twelve-member roster) | `brain/mesh/index.yaml` |
| Algorithms | `algorithm.*` | `brain/mesh/index.yaml` |
| Loops | `loop.*` (attl-mesh, trading-swarm, repair, …) | `brain/mesh/index.yaml` |
| Spines | `spine.*` | `brain/mesh/index.yaml` |
| Companion repos | `repo.*` | `brain/mesh/repos.yaml` |
| Runtime endpoints | `endpoint.*` (broker OpenD/Alpaca, LLM, dashboard, ntfy, vault, VisualHFT, …) | `Config` |
| Anchors | `anchor.*` (user, brain, vault, brief, factory, maker) | built-in |

Edges carry a relation (`feeds`, `owns`, `serves`, `notifies`, `persists`)
derived from member feeds, algorithm owners, loop feeds, spine owners, and
endpoint wiring. Building the mesh is fully offline — no sockets are opened.

## Memory and persistence

Every node and edge carries a weight in `[0, 1]` (prior `0.5`). When a run is
recorded, the activated nodes — and the edges between co-activated nodes —
move toward `1.0` on success and `0.0` on failure (EMA, learning rate `0.2`).
A bounded history of the last 200 runs is kept for recall.

State persists under `data/{env}/mesh/`:

- `memory.json` — node/edge weights + run history (survives sessions)
- `graph.json` — last materialized graph snapshot

`aoa attl run` feeds the memory automatically after every cycle (best-effort;
memory failures never break the loop). Outcomes `paused` and
`critical-report` reinforce as failures; everything else as success.

## CLI

```bash
aoa mesh status                 # graph size, kinds, learned weights, health, weakest nodes
aoa mesh sync                   # rebuild graph + persist to data/{env}/mesh/
aoa mesh recall member.reed     # remembered runs touching a node
```

All subcommands accept `--json`.

## Module

`src/aoa/mesh/graph.py` — `NeuralEndpointMesh`, `MeshMemory`, `MeshNode`,
`MeshEdge`. Tests: `tests/test_endpoint_mesh.py`.
