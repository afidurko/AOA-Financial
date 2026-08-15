# Decision: Jim & Cindy vs ATTL twelve

**Date:** 2026-08-15  
**Status:** Accepted  
**Related:** PR #60 (Jim & Cindy overlay), ATTL auto-12 (#58)

## Decision

Keep the canonical **ATTL twelve-member** mesh unchanged (`TWELVE_MEMBER_ROSTER`,
Nova / Reed / Kai, `len == 12` tests, loop-constraints).

**Jim** (short-term technical) and **Cindy** (company profitability) are
**specialist analysts outside the ATTL twelve**:

- They run in the team analysis pipeline and feed Alan’s brief.
- They own the dashboard **Jim & Cindy** overlay tab.
- They are **not** members of `TWELVE_MEMBER_ROSTER` / Aaron’s CEO twelve.
- Expansion profiles may still list them as leads for sub-team proposals.

## Why

ATTL auto-12 locked a fixed meshed roster and critical-only Kai review. Expanding
to fourteen would rename the `TWELVE_*` invariant and rewrite constraints/brain
docs. Specialist-outside-twelve preserves both product intents without breaking
the mesh.

## Follow-ups

- Dashboard Team tab may show Jim/Cindy (analysts) alongside Nova/Reed/Kai (ATTL).
- Aaron’s system prompt remains the twelve-member ATTL framing.
