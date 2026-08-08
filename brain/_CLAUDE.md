# AOA Second Brain — operating rules

This `brain/` workspace is the living second brain for AOA-Financial agents.
It meshes with `vault/`, trading algorithms, and the 12-member ATTL team.

Inspired by spine (feature spines) and obsidian-second-brain (self-rewriting notes).

## Rules

1. **Capture over chat memory** — durable facts go into `captures/` or a spine note.
2. **Spine first** — read `spine/*.md` before deep-diving a feature.
3. **Mesh is source of truth for edges** — update `mesh/index.yaml` when roles or algorithm links change.
4. **Rewrite, don't only append** — reconcile contradictions in spine notes.
5. **Critical-only noise** — routine ATTL runs log a short capture; full reports only on critical/system failure.
6. **User can always override** — Aaron Fidurko may edit any note; agents re-sync on next `aoa attl brain sync`.
7. **Hard safety floor** — never store secrets, API keys, or live credentials here.

## Who writes here

| Agent | Writes |
|-------|--------|
| Nova | mesh graph, spine health, vault mirror |
| Reed | task-loop captures, implementation notes |
| Kai | critical failure reports under `captures/critical-*.md` |
| Julie | algorithm mesh links when signals change |
| Alex | priority digests when BRIEF requests brain context |
