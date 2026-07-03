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

Also available: `/connect-chrome`, `/setup-deploy`, `/setup-gbrain`, `/codex`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`.
