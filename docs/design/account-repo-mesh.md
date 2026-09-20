# Account repo mesh — what each GitHub repo contributes to AOA

**Scope:** full sweep of the `afidurko` account (89 repos, 2026-09-20), mapping
every repo to how it is (or is not) applied inside AOA-Financial. Newly applied
repos feed the **crypto trader swarm** (`aoa.crypto.traders`); previously
applied repos are listed for completeness.

## Newly applied (this pass — the trader swarm)

| Repo | What was distilled | Where |
|------|--------------------|-------|
| **GHOST** (sentiment-gated Mamba, ESWA 2026) | Input-**selective gating**: the state-update strength is a learned function of the input, so the model chooses per step how much history to keep. | `aoa.crypto.deep.GatedReservoir` (gate + readout train online; echo-state reservoir keeps recurrence stable without BPTT) |
| **Deep-Learning--Stock-Market-Prediction** (Mamba vs LSTM) | Recurrent vs feed-forward predictor comparison — run live inside the swarm; the Hedge weights *are* the ongoing comparison. | `ReservoirTrader` vs `DeepMLPTrader` roster members |
| **deepstock / Stock-Price-Prediction / stock-risk-analyzer** | Deep feed-forward next-day return prediction on engineered features. | `aoa.crypto.deep.DeepMLP` (full backprop, SGD+momentum, arbitrary depth) → `DeepMLPTrader` ×2 depths |
| **Stock-Market-App** (SARIMA/RF forecasting) | Classical autoregressive baseline every deep model must beat. | `ARTrader` — online AR(5) on scaled returns |
| **Pairs-Trading-Analyzer** (Engle-Granger cointegration) | Relative-value mean reversion: z-score of the log price ratio vs an economically-paired partner (BTC↔ETH, SOL↔ETH, XRP↔BTC); buy the cheap leg, exit the rich one. | `PairsTrader` + `PAIR_PARTNERS` |
| **AutoHedge** (autonomous hedge-fund swarm) | Director/Quant/Risk/Execution decomposition → specialized traders + risk gate + executor; trust flows to what works. | `HedgeEnsemble` — **multiplicative-weights (Hedge)** supervisor with persistent per-trader weights |
| **OpenAI_Agent_Swarm** (HAAS) | Hierarchical supervisor over autonomous agents. | The ensemble layer itself (`decide_full` fuses weighted votes) |
| **lifelines / scikit-survival** | Survival analysis with censoring → first-passage race between the +32% target and the −26% stop, per regime. | `aoa.crypto.survival.BracketSurvival` — online Kaplan-Meier-style outcome tables gating ensemble entries |

## Previously applied (already meshed)

| Repo | Where |
|------|-------|
| VisualHFT | `aoa visualhft` lane |
| hft (C++ HFT) | `aoa.research.hft_patterns` |
| SGX-Full-OrderBook-Tick-Data-Trading-Strategy | `aoa.research.sgx_orderbook_patterns` |
| example-hftish | `aoa.research.hftish_patterns` |
| open-quant-live-book | `aoa.research.open_quant_patterns` |
| avellaneda-stoikov | `aoa avellaneda` lane |
| hftbacktest | optional `[hftbacktest]` extra, `aoa hft` |
| HFT-Orderbook | vendored `aoa.orderbook.vendor.lob` |
| FinancePy | optional extra for Andrea's options context |
| py-moomoo-api | broker SDK |
| cli (alpaca) | `aoa.brokerage.alpaca_cli_profile` |
| deepstock | `docs/how-to/deepstock-reference.md` |
| loop-engineering | `LOOP.md` scaffold |
| waste / qm / spine / obsidian-second-brain | companion mesh (`aoa workspaces`) |

## Reviewed, not applied (out of scope for a trading system)

* **Agent/infra tooling** — cline, SuperAGI, sgr-agent-core, agentrq, LitServe,
  higgsfield, nullclaw/nullhub/nullboiler/nulltickets, illa-builder,
  electron-builder, codebase-memory-mcp, inkbox, MemoryBear,
  smart-second-brain, llm-checker, Jarvis, Personal-Assistant, Assistant-,
  azure-serverless-workshop: app/agent scaffolding — AOA already has its own
  swarm, CLI, and web dashboard; nothing trading-specific to distill.
* **Voice/vision/health** — VoiceStudio, FunASR, pupil, PaddleDetection,
  lidar_camera_calibration, LLMAvatarTalk, AI-assitant-with-Opencv,
  CardioGaurd, ECG, ecg-classification, qrs_detector: different domains.
* **Collectibles/cards** — all Pokémon/TCG/sports-card repos (CollectorVision,
  CardScryer, Pregrader, joshinator-analyzer, sports-card-agent, …): different
  asset class; the pricing/valuation ideas do not transfer to liquid crypto.
* **Marketing packs** — ai-marketing-*, marketingskills, advertools, etc.: not
  code paths for trading.
* **Misc** — public-apis (catalog), tailscale, aframe, SwiftGuide,
  ant-design-mobile, kivy_pokemon, cards-database, pokeapi: unrelated.

Note: **GHOST**'s GDELT sentiment feed and **AutoHedge**'s live Solana
execution were deliberately *not* ported — the first needs an external data
subscription, the second violates the Hard Safety Floor (no live orders from
loops). Only their architectures were distilled.
