"""AOA Financial — an autonomous agentic swarm for stock & options trading.

The package is organized into clear layers:

- ``brokerage`` — abstract broker interface + Alpaca implementation. The broker
  is both the *information source* (quotes, bars, account, positions, option
  chains) and the *order executor*.
- ``data`` — market-data assembly and pure-Python technical indicators.
- ``llm`` — a thin wrapper around the Anthropic Claude API used by every agent.
- ``agents`` — specialized reasoning agents (scanner, technical, fundamental,
  options strategist, risk manager, portfolio manager).
- ``swarm`` — the orchestrator and shared blackboard that coordinate the agents.
- ``risk`` — hard, deterministic guardrails for a cash account.
- ``execution`` — turns approved decisions into broker orders.
- ``journal`` — append-only record of every decision and trade.
"""

__version__ = "0.1.0"
