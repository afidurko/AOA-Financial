"""Multi-agent swarm decision layer."""
from .agents import AgentSignal, run_agents
from .decision import SwarmDecision, decide, analyze_ticker, evaluate

__all__ = ["AgentSignal", "run_agents", "SwarmDecision", "decide",
           "analyze_ticker", "evaluate"]
