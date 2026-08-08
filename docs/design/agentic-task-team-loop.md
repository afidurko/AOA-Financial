# Design: Agentic Task-Team Loop (ATTL)

> **Status:** Active — constraints + mesh unified (Hard Floor + Auto-12)  
> **Owner:** Aaron Fidurko  
> **Cross-repo inputs:** `loop-engineering`, `spine`, `obsidian-second-brain`, `AutoHedge`, AOA vault

## Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Autonomy | **Jump to auto** — 12-member meshed team |
| 2 | Process constraints | **Relaxed** — user interacts directly and can fix; hard safety floor only (secrets / live / pause) |
| 3 | Review policy | **Critical-only** — review/report when critical flaw, system failure, or explicit report needed |
| 4 | Knowledge | **New `brain/` workspace** — second brain, meshed with vault + algorithms |
| 5 | Delivery | **Prioritize by need/application** (below) |

## Priority order (need → application)

| P | Workstream | Why first |
|---|------------|-----------|
| **P0** | `brain/` second-brain workspace + mesh graph | Algorithms and agents need a shared memory surface |
| **P1** | 12-member roster with unique meshing roles | Team must exist before auto loops run |
| **P2** | ATTL auto runtime + critical-only review | Unblocks unattended coding task loops |
| **P3** | Task factory auto-create from repair/backlog | Feeds the loop without manual YAML |
| **P4** | Algorithm integration (`brain_context_for_algorithms`) | Mesh knowledge into Julie/Tom/signal path |
| **P5** | BRIEF/iPhone report channel for critical events | User visibility without mandatory review |

## One-line intent

Auto-create and run coding task loops with a **12-member meshed agentic team**, writing into a **second-brain workspace** that algorithms can read — reviewing **only** on critical failure, system failure, or when a report is needed. User remains able to intervene at any time.

---

## Twelve-member meshed team

Existing nine trading/ops members plus three ATTL specialists:

| # | Member | Unique role | Mesh edges (feeds →) |
|---|--------|-------------|----------------------|
| 1 | **Tom** | Trend Analyst | Julie, Alan |
| 2 | **Julie** | Algorithm Specialist & Code Clarity | Alan, Reed, brain/algorithms |
| 3 | **Morgan** | Market & Volume Analyst | Alan, Hailey |
| 4 | **Hailey** | News & Catalyst Analyst | Alan, Andrea |
| 5 | **Alan** | Decision Aggregator & Code Oversight | Aaron, Reed |
| 6 | **Andrea** | Risk Manager & Pre-Execution | Aaron, Bob |
| 7 | **Bob** | Systems Health & Code Integrity | Aaron, Kai, Reed |
| 8 | **Aaron** | CEO (remediate / escalate) | User, Alex |
| 9 | **Alex** | Executive Assistant (priorities) | User, BRIEF |
| 10 | **Nova** | Second-Brain / Knowledge Mesh Curator | brain/, vault, all leads |
| 11 | **Reed** | Task-Loop Architect & Implementer | factory, maker path, Julie |
| 12 | **Kai** | Critical Failure Sentinel | Bob, Aaron — **only** on critical |

Meshing rule: each member has a distinct job; outputs are typed edges in `brain/mesh/index.yaml`. No duplicate “generic reviewer” roles.

### Critical-only review (Kai)

Kai (and full team review) runs **only** when any of:

- Critical code/health flaw (`Bob.can_proceed == false`, severity critical)
- System failure (gate `pause`, verify crash, worktree failure)
- Explicit report requested (`aoa attl report` or BRIEF critical section)

Otherwise Reed proceeds auto → draft PR / chain advance; user can fix later.

---

## Second brain workspace (`brain/`)

Inspired by **spine** (feature spines) + **obsidian-second-brain** (living vault) + AOA **vault** sync:

```
brain/
  _CLAUDE.md              # agent operating rules for this workspace
  README.md
  spine/                  # feature entry points (wikilink-style)
  mesh/index.yaml         # machine-readable graph (agents ↔ algos ↔ notes)
  mesh/repos.yaml         # cross-repo aids (loop-engineering, spine, …)
  captures/               # auto-captured run notes
  decisions/              # decision records
```

Python: `aoa.brain` — ensure workspace, load mesh, expose `brain_context_for_algorithms()`.

Vault note `vault/brain/mesh.md` mirrors mesh health via analyzer `brain_mesh`.

---

## Auto ATTL runtime

```
gate (pause only hard-stop)
  → Nova syncs brain mesh
  → Reed proposes + picks next coding task (repair queue / backlog)
  → worktree + implement (maker)
  → Bob quick health
  → if critical/system-fail → Kai review + Aaron report to user
  → else auto-continue (draft PR / chain advance)
  → capture into brain/captures
```

Usage mode default: **`auto-12`**.

Hard safety floor (not process bureaucracy):

- `loop-pause-all` still stops everything
- Never edit `.env*`, secrets, `profiles/live.env`, or disable `risk/guards.py`
- Never auto-merge to `main` without user (draft PR remains)

---

## Cross-repo utilization

| Repo | What we take |
|------|----------------|
| `loop-engineering` | Pattern registry, L1/L2 loop shapes, budget/audit mindset |
| `spine` | Feature-first spine notes under `brain/spine/` |
| `obsidian-second-brain` | `_CLAUDE.md` living-brain rules, capture/distill habits |
| `AutoHedge` | Swarm/worker role separation patterns for meshing |
| AOA `vault/` | Property sync + analyzers; brain mirrors into vault |

---

## CLI

```bash
aoa attl init          # ensure brain/ + mesh + default config (auto-12)
aoa attl status        # mode, roster, pending criticals, mesh stats
aoa attl roster        # print 12-member mesh
aoa attl run [--dry-run]
aoa attl propose       # Reed: create tasks from repair/backlog (auto-queued)
aoa attl report        # force Kai/Aaron report path
aoa attl brain sync    # Nova: refresh mesh + vault mirror
```

---

## Acceptance (this delivery slice)

1. `brain/` exists with spine + mesh + `_CLAUDE.md`.
2. Roster is exactly 12 unique roles; Aaron CEO report includes all twelve.
3. `aoa attl init|status|roster|run|propose|brain sync` work.
4. Default mode `auto-12`; review skipped unless critical detector fires.
5. `brain_context_for_algorithms()` returns mesh snippets for algorithm path.
6. Tests cover roster size, critical gate, brain ensure/sync, CLI smoke.
