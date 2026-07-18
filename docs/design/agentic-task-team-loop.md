# Design: Agentic Task-Team Loop (ATTL)

> **Status:** Proposed — awaiting Aaron (user) approval before implementation  
> **Owner:** Aaron Fidurko  
> **Related:** [LOOP.md](../../LOOP.md) · [fable5-repair-loop.md](../fable5-repair-loop.md) · [loop-automation-schedule.md](../how-to/loop-automation-schedule.md) · `src/aoa/workloop/team_review.py`

## One-line intent

Automatically **create**, **queue**, and **run** coding task loops, then have a **five-member agentic team** proofread and fix the resulting code — with the **human user as the ultimate usage gate** (activate, pause, approve, reject, or take over at any time).

---

## Why this exists

Today AOA has strong pieces that do not yet form one product:

| Piece | What it does today | Gap |
|-------|-------------------|-----|
| `aoa tasks` + `loop-prompts.yaml` | Static shortkeys + deterministic runners | No auto-creation of new task loops |
| `aoa repair` + fable-repair | Discover → maker → checker → draft PR | No five-member proofread on coding tasks |
| `aoa workloop` + `team_review` | Bob→Julie→Alan→Aaron→user on dependency/work changes | Not wired into repair / task-chain coding work |
| `tasks automations` | Prints paste-ready Cursor specs | No “propose → user activate” lifecycle |
| BRIEF + iPhone | Surfaces priorities | Approvals are split across workloop / draft PR / STATE.md |

**Target product:** one control plane where tasks are born, reviewed by the five-member coding team, implemented under maker/checker rules, and never used against the user’s will.

---

## Non-negotiable principles

1. **User is ultimate say** — no new automation, cadence, or auto-fix path goes live without explicit user activation (or a prior standing policy the user recorded).
2. **Maker ≠ checker** — the agent that writes code never grades it.
3. **Five-member coding review is mandatory** for coding-task outputs before draft PR is marked ready for human merge consideration.
4. **Draft PR only** — never auto-merge to `main`.
5. **Kill switch** — `loop-pause-all` in `STATE.md` stops everything immediately.
6. **Denylist absolute** — `.env*`, secrets, live trading, `src/aoa/risk/guards.py` never auto-touched.
7. **One coding fix per autonomous run** (budget + blast-radius control).
8. **Fail closed** — missing approval, failed team review, or budget breach → report-only / escalate.

---

## The five-member coding team

Distinct from the **trading** five (Tom / Julie / Bob / Alan / Aaron).

| # | Member | Role in ATTL | Mechanism |
|---|--------|--------------|-----------|
| 1 | **Bob** | Code integrity & import/health gate | Deterministic `run_code_quality_audit` |
| 2 | **Julie** | Scope, clarity, sensitive-path / blast-radius | Rules + optional LLM deep review |
| 3 | **Alan** | Aggregate approve / reject / escalate_user | Structured LLM or rules fallback |
| 4 | **Aaron (CEO agent)** | Verdict + required approver + notifications | Structured LLM or rules; iPhone on escalate |
| 5 | **User (Aaron Fidurko)** | Ultimate usage & merge authority | Activate loops, approve escalations, merge PRs |

Verdict ladder:

```
reject          → stop; log; no PR
approve         → proceed to draft PR; user still merges
escalate_user   → pause implementation / hold PR; notify user; await aoa attl approve
```

Even on `approve`, **usage** (whether the automation may keep running tomorrow) remains a user policy in `STATE.md` / ATTL config — not an agent decision.

---

## Target architecture

```
                    ┌──────────────────────────────────────┐
                    │  USER CONTROL PLANE                  │
                    │  activate / pause / approve / reject │
                    │  STATE.md · aoa attl · BRIEF/iPhone  │
                    └───────────────┬──────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌─────────────────┐      ┌────────────────────┐      ┌─────────────────┐
│ Task Factory    │      │ Workflow Engine    │      │ Proofread Team  │
│ create/propose  │─────▶│ queue → worktree   │─────▶│ Bob Julie Alan  │
│ backlog+YAML    │      │ maker → verifier   │      │ Aaron → User    │
│ paste automations│      │ draft PR           │      │                 │
└─────────────────┘      └────────────────────┘      └─────────────────┘
         │                          │                          │
         └──────────────────────────┴──────────────────────────┘
                                    │
                         Unified Approvals Store
                         data/{env}/attl/approvals.json
```

### Three subsystems

#### 1. Task Factory (`aoa attl define` / propose)

**Creates** task-loop definitions from signals (repair queue, upgrade backlog, CI failures, human intent) but does **not** enable them.

Outputs (all draft until user activates):

- Prompt shortkey candidate → pending section of `loop-prompts.yaml` or `data/{env}/attl/proposed-prompts.yaml`
- Optional deterministic `tasks:` runner steps
- Optional Cursor automation export block (`aoa tasks automations` style)
- Backlog / chain item id

**User activation:**

```bash
aoa attl propose --from repair|backlog|stdin   # agents may call this
aoa attl list --status proposed
aoa attl activate <id>                         # USER only (or human-in-the-loop)
aoa attl deactivate <id>
aoa attl reject <id> --note "..."
```

Until `activate`, schedules and L2 runners ignore the definition.

#### 2. Workflow Engine (extends repair + task chain)

Canonical coding-task pipeline (L2):

```
gate → pick ONE item → worktree
  → maker (minimal-fix / coding-engineer)
  → checker (loop-verifier, fresh context)
  → five-member proofread (team_review on the diff)
  → if approve: draft PR
  → if escalate_user: hold + notify; await aoa attl approve
  → chain advance (only after PR opened or user skip)
```

Reuse existing primitives:

- `aoa repair triage` / `worktree` / schedule gate
- `aoa tasks chain *`
- Cursor skills: `fable-repair`, `minimal-fix`, `loop-verifier`
- New shared module: promote `review_change_proposal` from workloop-only to shared coding-review API

#### 3. Proofread Team (shared module)

Extract / generalize `src/aoa/workloop/team_review.py` → e.g. `src/aoa/team/code_review.py` used by:

- workloop (existing)
- ATTL / fable-repair coding tasks (new)
- optional `aoa attl review --pr <n>` for human-triggered re-review

Store each review verdict on the task / repair item so BRIEF can surface “awaiting your approval”.

---

## Unified approvals model

One store for pending human decisions:

```json
{
  "id": "appr-20260718-01",
  "kind": "activate_task|coding_escalation|merge_ready",
  "subject_id": "task-… or repair-…",
  "required_approver": "user",
  "status": "pending|approved|rejected",
  "created_at": "…",
  "summary": "…",
  "actions": {
    "approve_cli": "aoa attl approve appr-20260718-01",
    "reject_cli": "aoa attl reject appr-20260718-01"
  }
}
```

Surfacing channels (user chooses which are on):

| Channel | Behavior |
|---------|----------|
| `STATE.md` High Priority | Always |
| Automation C BRIEF + iPhone | When configured |
| `aoa attl pending` | CLI inbox |
| Draft PR body checklist | Coding outcomes |

Inbound alert replies (existing `/api/alerts/{id}/respond`) may map to approve/reject **only** for ATTL approval ids — never for merge/.env.

---

## Usage modes (user ultimate say)

Recorded under `STATE.md` → `## Loop automation` and/or `data/{env}/attl/config.json`:

| Mode | Meaning |
|------|---------|
| `off` | Factory may propose; nothing schedules or auto-fixes |
| `propose-only` | Daily propose + BRIEF; user activates manually |
| `auto-l2-scoped` | Current L2 policy: auto-fixable code-health only; still draft PR |
| `auto-l2-with-team` | L2 + mandatory five-member proofread before PR |
| `paused` | Equivalent to `loop-pause-all` |

**Default after merge of this design:** `propose-only` until user runs `aoa attl mode auto-l2-with-team` (or edits STATE). No silent upgrade of autonomy.

---

## CLI surface (proposed)

```bash
# Factory
aoa attl propose [--from repair|backlog|file]
aoa attl list [--status proposed|active|rejected]
aoa attl show <id>
aoa attl activate <id>          # user
aoa attl deactivate <id>        # user
aoa attl reject <id>            # user
aoa attl mode <mode>            # user — usage policy

# Workflow
aoa attl run [--dry-run]        # one full coding-task cycle if mode allows
aoa attl status
aoa attl pending                # approvals inbox

# Proofread / approvals
aoa attl review --item-id <id>  # run five-member review on current diff
aoa attl approve <approval-id>
aoa attl deny <approval-id>
```

Compatibility: keep `aoa tasks`, `aoa repair`, `aoa workloop` as lower-level tools; ATTL orchestrates them. Existing Automations A/B/C remain valid; new prompts (`ATTL`, `ATTL-PROPOSE`) added to `loop-prompts.yaml` after user activation.

---

## Data & files

| Path | Role |
|------|------|
| `data/{AOA_ENV}/attl/config.json` | Usage mode, feature flags |
| `data/{AOA_ENV}/attl/definitions.json` | Proposed/active task definitions |
| `data/{AOA_ENV}/attl/approvals.json` | Unified approvals |
| `data/{AOA_ENV}/attl/runs/` | Per-run artifacts (review JSON, gate JSON) |
| `loop-prompts.yaml` | Only **active** shortkeys (activated definitions may sync here) |
| `STATE.md` | Human-readable mode + pending approvals summary |
| `loop-run-log.md` | New Loop column value: `attl` |

---

## Phased delivery

### Phase 0 — Plan lock (this PR)

- Design doc (this file)
- Pattern registry entry
- Upgrade backlog items
- LOOP.md link
- **No behavior change** until user approves and Phase 1 lands

### Phase 1 — Shared proofread API

- Extract `review_change_proposal` to shared `aoa.team.code_review` (or keep import facade)
- Wire into fable-repair path **behind flag** `AOA_ATTL_TEAM_REVIEW=false` default
- Tests: repair item with mock diff → Bob/Julie/Alan/Aaron verdict; escalate_user blocks PR helper
- Docs: update fable5-repair-loop.md

### Phase 2 — Task Factory (propose / activate)

- `aoa attl propose|list|show|activate|deactivate|reject|mode`
- Persist definitions; never auto-activate
- Export paste block for Cursor automation
- BRIEF lists proposed definitions awaiting activation
- Tests for lifecycle + fail-closed activate

### Phase 3 — Workflow composition

- `aoa attl run` composes gate → worktree → maker/checker skills handoff notes → team review → draft-PR checklist
- New `run_task` steps: `team-review`, `await-user-approval` (deterministic waits / status, not silent proceed)
- Prompt shortkeys `ATTL` / `ATTL-PROPOSE` (inactive until mode allows)
- Update Automation B prompt to optional team-review step when mode = `auto-l2-with-team`

### Phase 4 — Unified approvals + UX

- Approvals store + `aoa attl pending|approve|deny`
- Map iPhone / BRIEF / alert respond → approval ids
- Dashboard snippet (optional web) for pending ATTL items
- Diataxis how-to: “Activate your first agentic task loop”

### Phase 5 — Hardening

- Budget integration (`loop-budget.md` ATTL caps)
- Concurrent A/B/STATE race fixes
- Clarify naming in docs: trading-five vs coding-five
- Pattern registry + `/document-release` pass

---

## Explicit non-goals (v1)

- Auto-merge to `main`
- Auto-registration against a Cursor Automations HTTP API (paste + user click remains)
- Letting trading swarm (`aoa loop`) modify application code
- Replacing workloop; ATTL **reuses** its team review, does not delete it
- Silent L3 / unbounded multi-file refactors

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Autonomy creep | Default `propose-only`; activate is user CLI/STATE only |
| Two “five-member” teams confuse operators | Docs glossary; coding team always includes **User** as #5 |
| Token burn from double review (verifier + team) | Team review runs once post-verifier; budget caps; dry-run mode |
| STATE.md races | Single writer helpers; ATTL section with stable anchors |
| Julie rules-only too weak for “proofread” | Phase 1 flag for LLM Julie on coding diffs when API key present |
| User offline on escalate | Hold PR; BRIEF retries; never merge |

---

## Acceptance criteria (product done)

1. User can go from “idea / repair signal” → proposed task loop → **activate** → one coding run → five-member proofread → draft PR without editing skill prose by hand.
2. With mode `off` or `propose-only`, no code changes occur unattended.
3. `escalate_user` always blocks progress until `aoa attl approve` (or equivalent).
4. `loop-pause-all` stops ATTL propose and run.
5. Existing L1/L2 automations keep working unchanged when ATTL mode is `off`.
6. Tests cover factory lifecycle, team-review gate, and approval fail-closed paths.

---

## Decision requests for Aaron (approve before build)

Please confirm or amend:

1. **Default mode after Phase 1–2 merge:** `propose-only` (recommended) vs jump to `auto-l2-with-team`.
2. **Coding five membership:** Bob / Julie / Alan / Aaron-agent / **User** (recommended) vs insert Tom or Alex instead of User-as-member (User would still remain ultimate merge gate either way).
3. **When team review runs:** after `loop-verifier` only (recommended) vs also before maker (plan review).
4. **CLI namespace:** `aoa attl …` (recommended) vs fold under `aoa tasks …`.
5. **Phase ordering:** 1→2→3→4 as above, or Factory (2) before shared review (1)?

Reply on the PR or via BRIEF / `aoa attl` once Phase 2 exists. Until then, this document is the source of truth for the restructure.

---

## Appendix A — Mapping to existing commands

| Today | ATTL relationship |
|-------|-------------------|
| `aoa tasks show L2` | Becomes one active definition among many |
| `aoa repair triage` | Discovery input to Factory + Workflow |
| `aoa workloop` | Sibling loop; shares proofread module |
| `fable-repair` skill | Workflow orchestrator skill updated in Phase 3 |
| `loop-constraints.md` | Gains ATTL bullets in Phase 1 (user still ultimate) |

## Appendix B — Glossary

- **ATTL** — Agentic Task-Team Loop (this design)
- **Factory** — proposes task definitions; cannot enable itself
- **Workflow** — executes one coding task under gates
- **Proofread team** — Bob, Julie, Alan, Aaron-agent, User
- **Usage mode** — user policy for how automatic the system may be
