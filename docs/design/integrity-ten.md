# Design: Integrity Ten — cohesive integrity mesh

> **Status:** Active — meshed into ATTL auto-12  
> **Owner:** Aaron Fidurko  
> **CLI:** `aoa integrity status|roster|run|watch|approve|reject`

## Intent

A **10-agent cohesive unit** continuously checks:

1. **Code integrity** (Bob + Julie)
2. **Companion workspace mesh** (Nova)
3. **Neural memory** — `brain/` + plasticity (Nova)
4. **Mesh cohesion** — Integrity Ten ↔ twelve-member roster (Alan)

When issues arise, the squad **prepares a corrective action** and **notifies the user**.  
Corrective action is **implanted only after** `aoa integrity approve <id>` (or rejected).

Tom and Morgan stay on market lanes; they are not on the Integrity Ten.

## Roster (Integrity Ten)

| # | Member | Integrity role | Domain |
|---|--------|----------------|--------|
| 1 | Julie | Algorithm & Code Clarity Integrity | algorithms |
| 2 | Hailey | Docs & Companion Mesh Integrity | docs |
| 3 | Alan | Mesh Cohesion Aggregator | cohesion |
| 4 | Andrea | Hard Safety Floor Integrity | safety |
| 5 | Bob | Code & Systems Integrity | code |
| 6 | Aaron | Corrective Notification Lead | notify |
| 7 | Alex | Approval BRIEF Router | approvals |
| 8 | Nova | Neural Memory & Workspace Mesh | neural_memory |
| 9 | Reed | Corrective Implementer | fix |
| 10 | Kai | Critical Integrity Sentinel | critical |

## Cycle

```
constraints / pause check
  → domain checks (code, algorithms, docs, safety, neural memory, workspaces, cohesion)
  → Kai only if critical
  → if issues: queue CorrectiveProposal + Aaron notification (requires_response)
  → user: approve → safe implant + Reed draft-PR handoff
         reject → no implant
  → brain/captures note
```

## Hard floor (unchanged)

- Never auto-merge
- Never edit `.env*`, secrets, `profiles/live.env`, or weaken `risk/guards.py`
- `loop-pause-all` halts Integrity Ten

## CLI

```bash
aoa integrity roster
aoa integrity status
aoa integrity run              # one cycle; notify if action needs approval
aoa integrity watch --interval 300
aoa integrity queue            # list pending corrective proposals
aoa integrity queue --push     # notify user about pending queue
aoa integrity approve <id>     # implant corrective action
aoa integrity reject <id>      # decline
```

## Queue notifications

Aaron pushes queue alerts when a channel is configured:

1. **ntfy (easiest):** install the ntfy iPhone app → subscribe to a private topic → set `AOA_NTFY_TOPIC` in `.env` (never commit secrets).
2. **Pushover:** `AOA_PUSHOVER_USER_KEY` + `AOA_PUSHOVER_APP_TOKEN`
3. **Custom app:** real `AOA_CUSTOM_APP_WEBHOOK_URL` (placeholder `example.com` URLs are ignored)

Toggle: `AOA_INTEGRITY_NOTIFY_QUEUE=true` (default). Check: `aoa integrity status`.

## Acceptance

1. Roster is exactly 10 unique names, all subset of the twelve-member roster.
2. `aoa integrity run` produces domain reports without requiring a live broker.
3. Non-OK findings create a pending proposal; implant requires explicit approve.
4. Approve writes a brain capture and optional Reed handoff; never merges.
5. `aoa integrity queue --push` notifies via configured channels (or reports setup hint).
6. Tests cover roster size, cohesion check, propose/approve/reject, queue notify, CLI smoke.
