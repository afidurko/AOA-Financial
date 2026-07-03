"""Agent team — bundles specialist agents for the swarm pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from aoa.agents.fund_manager import FundManagerAgent
from aoa.agents.fundamental import FundamentalAgent
from aoa.agents.meshing import MeshingAgent
from aoa.agents.news_analyst import NewsAnalystAgent
from aoa.agents.options import OptionsStrategistAgent
from aoa.agents.portfolio import PortfolioManagerAgent
from aoa.agents.research import ResearchTeamAgent
from aoa.agents.risk import RiskManagerAgent
from aoa.agents.risk_debate import RiskDebateTeamAgent
from aoa.agents.scanner import ScannerAgent
from aoa.agents.sentiment import SentimentAnalystAgent
from aoa.agents.technical import TechnicalAgent
from aoa.brokerage.base import Broker
from aoa.config import RiskLimits
from aoa.llm.client import LLMClient


@dataclass
class AgentTeam:
    """All reasoning agents wired for one orchestrator / pipeline run."""

    scanner: ScannerAgent
    technical: TechnicalAgent
    fundamental: FundamentalAgent
    news: NewsAnalystAgent
    sentiment: SentimentAnalystAgent
    research: ResearchTeamAgent
    meshing: MeshingAgent
    options: OptionsStrategistAgent
    portfolio: PortfolioManagerAgent
    risk: RiskManagerAgent
    risk_debate: RiskDebateTeamAgent
    fund_manager: FundManagerAgent

    @classmethod
    def from_llm(cls, llm: LLMClient, broker: Broker, *, risk: RiskLimits) -> AgentTeam:
        return cls(
            scanner=ScannerAgent(llm),
            technical=TechnicalAgent(llm),
            fundamental=FundamentalAgent(llm),
            news=NewsAnalystAgent(llm),
            sentiment=SentimentAnalystAgent(llm),
            research=ResearchTeamAgent(llm),
            meshing=MeshingAgent(llm),
            options=OptionsStrategistAgent(llm, broker),
            portfolio=PortfolioManagerAgent(llm),
            risk=RiskManagerAgent(llm, risk),
            risk_debate=RiskDebateTeamAgent(llm),
            fund_manager=FundManagerAgent(llm),
        )
