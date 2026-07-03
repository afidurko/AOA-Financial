# AOA Financial

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

### Workflow

**Think → Plan → Build → Review → Test → Ship → Reflect**

Each skill feeds into the next. `/office-hours` writes a design doc that `/plan-ceo-review` reads. `/plan-eng-review` writes a test plan that `/qa` picks up. `/review` catches bugs that `/ship` verifies are fixed. Nothing falls through the cracks because every step knows what came before it.

| Skill | Your specialist | What they do |
|-------|-----------------|--------------|
| `/office-hours` | YC Office Hours | Start here. Six forcing questions that reframe your product before you write code. Pushes back on your framing, challenges premises, generates implementation alternatives. Design doc feeds into every downstream skill. |
| `/plan-ceo-review` | CEO / Founder | Rethink the problem. Find the 10-star product hiding inside the request. Four modes: Expansion, Selective Expansion, Hold Scope, Reduction. |
| `/plan-eng-review` | Eng Manager | Lock in architecture, data flow, diagrams, edge cases, and tests. Forces hidden assumptions into the open. |
| `/plan-design-review` | Senior Designer | Rates each design dimension 0-10, explains what a 10 looks like, then edits the plan to get there. AI Slop detection. Interactive — one AskUserQuestion per design choice. |
| `/plan-devex-review` | Developer Experience Lead | Interactive DX review: explores developer personas, benchmarks against competitors' TTHW, designs your magical moment, traces friction points step by step. Three modes: DX EXPANSION, DX POLISH, DX TRIAGE. 20-45 forcing questions. |
| `/design-consultation` | Design Partner | Build a complete design system from scratch. Researches the landscape, proposes creative risks, generates realistic product mockups. |
| `/review` | Staff Engineer | Find the bugs that pass CI but blow up in production. Auto-fixes the obvious ones. Flags completeness gaps. |
| `/investigate` | Debugger | Systematic root-cause debugging. Iron Law: no fixes without investigation. Traces data flow, tests hypotheses, stops after 3 failed fixes. |
| `/design-review` | Designer Who Codes | Same audit as `/plan-design-review`, then fixes what it finds. Atomic commits, before/after screenshots. |
| `/devex-review` | DX Tester | Live developer experience audit. Actually tests your onboarding: navigates docs, tries the getting started flow, times TTHW, screenshots errors. Compares against `/plan-devex-review` scores — the boomerang that shows if your plan matched reality. |
| `/design-shotgun` | Design Explorer | "Show me options." Generates 4-6 AI mockup variants, opens a comparison board in your browser, collects your feedback, and iterates. Taste memory learns what you like. Repeat until you love something, then hand it to `/design-html`. |
| `/design-html` | Design Engineer | Turn a mockup into production HTML that actually works. Pretext computed layout: text reflows, heights adjust, layouts are dynamic. 30KB, zero deps. Detects React/Svelte/Vue. Smart API routing per design type (landing page vs dashboard vs form). The output is shippable, not a demo. |
| `/qa` | QA Lead | Test your app, find bugs, fix them with atomic commits, re-verify. Auto-generates regression tests for every fix. |
| `/qa-only` | QA Reporter | Same methodology as `/qa` but report only. Pure bug report without code changes. |
| `/pair-agent` | Multi-Agent Coordinator | Share your browser with any AI agent. One command, one paste, connected. Works with OpenClaw, Hermes, Codex, Cursor, or anything that can curl. Each agent gets its own tab. Auto-launches headed mode so you watch everything. Auto-starts ngrok tunnel for remote agents. Scoped tokens, tab isolation, rate limiting, activity attribution. |
| `/cso` | Chief Security Officer | OWASP Top 10 + STRIDE threat model. Zero-noise: 17 false positive exclusions, 8/10+ confidence gate, independent finding verification. Each finding includes a concrete exploit scenario. |
| `/ship` | Release Engineer | Sync main, run tests, audit coverage, push, open PR. Bootstraps test frameworks if you don't have one. |
| `/land-and-deploy` | Release Engineer | Merge the PR, wait for CI and deploy, verify production health. One command from "approved" to "verified in production." |
| `/canary` | SRE | Post-deploy monitoring loop. Watches for console errors, performance regressions, and page failures. |
| `/benchmark` | Performance Engineer | Baseline page load times, Core Web Vitals, and resource sizes. Compare before/after on every PR. |
| `/document-release` | Technical Writer | Update all project docs to match what you just shipped. Catches stale READMEs automatically. Builds a Diataxis coverage map (reference / how-to / tutorial / explanation) so gaps are visible in the PR body. |
| `/document-generate` | Documentation Author | Generate missing docs from scratch using the Diataxis framework. Researches the codebase first, then writes reference / how-to / tutorial / explanation docs that actually match the code. Invokable standalone or chained from `/document-release` when the coverage map finds gaps. |
| `/retro` | Eng Manager | Team-aware weekly retro. Per-person breakdowns, shipping streaks, test health trends, growth opportunities. `/retro global` runs across all your projects and AI tools (Claude Code, Codex, Gemini). |
| `/browse` | QA Engineer | Give the agent eyes. Real Chromium browser, real clicks, real screenshots. ~100ms per command. `/open-gstack-browser` launches GStack Browser with sidebar, anti-bot stealth, and auto model routing. |
| `/setup-browser-cookies` | Session Manager | Import cookies from your real browser (Chrome, Arc, Brave, Edge) into the headless session. Test authenticated pages. |
| `/autoplan` | Review Pipeline | One command, fully reviewed plan. Runs CEO → design → eng review automatically with encoded decision principles. Surfaces only taste decisions for your approval. |
| `/spec` | Spec Author | Turn vague intent into a precise, executable spec in five phases (why, scope, technical with mandatory code-reading, draft, file). Codex quality gate before file (blocks below 7/10), fail-closed secret redaction, dedupe against existing issues, archive to `$GSTACK_STATE_ROOT/projects/$SLUG/specs/` for team-corpus recall. `--execute` spawns claude -p in a fresh worktree; `/ship` auto-closes the source issue on merge. Plan-mode aware. |
| `/learn` | Memory | Manage what gstack learned across sessions. Review, search, prune, and export project-specific patterns, pitfalls, and preferences. Learnings compound across sessions so gstack gets smarter on your codebase over time. |
| `/make-pdf` | Publisher | Markdown in, publication-quality document out. Mermaid and excalidraw fences render as vector diagrams, fully offline. Images scale to the page and never truncate; wide diagrams get their own landscape page. `--to html` emits one self-contained file, `--to docx` a Word doc. |
| `/diagram` | Diagram Maker | English in, editable diagram out. Emits a triplet: mermaid source, `.excalidraw` you can open and edit on excalidraw.com (hand-drawn style), and rendered SVG/PNG. Zero network. Embed the source in markdown and `/make-pdf` renders it. |

### Power tools

| Skill | What it does |
|-------|--------------|
| `/codex` | **Second Opinion** — independent code review from OpenAI Codex CLI. Three modes: review (pass/fail gate), adversarial challenge, and open consultation. Cross-model analysis when both `/review` and `/codex` have run. |
| `/careful` | **Safety Guardrails** — warns before destructive commands (`rm -rf`, `DROP TABLE`, force-push). Say "be careful" to activate. Override any warning. |
| `/freeze` | **Edit Lock** — restrict file edits to one directory. Prevents accidental changes outside scope while debugging. |
| `/guard` | **Full Safety** — `/careful` + `/freeze` in one command. Maximum safety for prod work. |
| `/unfreeze` | **Unlock** — remove the `/freeze` boundary. |
| `/open-gstack-browser` | **GStack Browser** — launch GStack Browser with sidebar, anti-bot stealth, auto model routing (Sonnet for actions, Opus for analysis), one-click cookie import, and Claude Code integration. Clean up pages, take smart screenshots, edit CSS, and pass info back to your terminal. |
| `/connect-chrome` | Alias for `/open-gstack-browser` (backwards compatible). |
| `/setup-deploy` | **Deploy Configurator** — one-time setup for `/land-and-deploy`. Detects your platform, production URL, and deploy commands. |
| `/setup-gbrain` | **GBrain Onboarding** — from zero to running gbrain in under 5 minutes. PGLite local, Supabase existing URL, or auto-provision a new Supabase project via Management API. MCP registration for Claude Code + per-repo trust triad (read-write/read-only/deny). |
| `/sync-gbrain` | **Keep Brain Current** — re-index this repo's code into gbrain via `gbrain sources add` + `gbrain sync --strategy code`, refresh the `## GBrain Search Guidance` block in CLAUDE.md, and auto-remove guidance when the capability check fails. `--incremental` (default), `--full`, `--dry-run`. Idempotent; safe to re-run. |
| `/gstack-upgrade` | **Self-Updater** — upgrade gstack to latest. Detects global vs vendored install, syncs both, shows what changed. |
| `/ios-qa` | **iOS Live-Device QA** (v1.43.0.0+) — drive a real iPhone over USB CoreDevice via an embedded StateServer in the app. Read Swift source, codegen typed `@Observable` accessors, run the agent loop. Optional `--tailnet` flag exposes the device to remote agents on your Tailscale tailnet. Capability-tier allowlist (observe/interact/mutate/restore), per-device session lock, audit log. |
| `/ios-fix`, `/ios-design-review`, `/ios-clean`, `/ios-sync` | iOS bug-fix loop, designer's-eye HIG audit, debug-bridge cleanup, and accessor resync. See gstack `docs/skills.md`. |

### Standalone CLIs

Beyond slash-command skills, gstack ships standalone CLIs for workflows that don't belong inside a session:

| Command | What it does |
|---------|--------------|
| `gstack-model-benchmark` | Cross-model benchmark — run the same prompt through Claude, GPT (via Codex CLI), and Gemini; compare latency, tokens, cost, and (optionally) LLM-judge quality score. Auth detected per provider; unavailable providers skip cleanly. Output as table, JSON, or markdown. `--dry-run` validates flags + auth without spending API calls. |
| `gstack-taste-update` | Design taste learning — writes approvals and rejections from `/design-shotgun` into a persistent per-project taste profile. Decays 5%/week. Feeds back into future variant generation. |
| `gstack-ios-qa-daemon` | iOS QA daemon — Mac-side broker between an agent and a connected iPhone over USB CoreDevice. Loopback by default; `--tailnet` opens a Tailscale-facing listener with identity-gated capability tiers. Single-instance via flock on `~/.gstack/ios-qa-daemon.pid`. |
| `gstack-ios-qa-mint` | iOS allowlist manager — owner-grant CLI for the tailnet allowlist. `grant`/`revoke`/`list` against `~/.gstack/ios-qa-allowlist.json` (mode 0600). Remote agents never auto-allowlist. |
