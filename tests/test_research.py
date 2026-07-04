"""Tests for Semantic Scholar research loop."""

from __future__ import annotations

from unittest.mock import patch

from aoa.analytics.store import AnalyticsStore
from aoa.config import Config, RiskLimits
from aoa.research.loop import ResearchLoop
from aoa.research.scholar import PaperHit, extract_technique_hint


def test_extract_technique_hint():
    paper = PaperHit(
        paper_id="1",
        title="Momentum strategies in equity markets",
        abstract="We study time-series momentum.",
        url="https://example.com",
        year=2020,
        citation_count=100,
    )
    assert extract_technique_hint(paper) == "momentum factor"


def test_research_loop_creates_proposals(tmp_path):
    cfg = Config(
        anthropic_api_key="x",
        scholar_enabled=True,
        scholar_query="momentum trading",
        scholar_max_results=2,
        analytics_db_path=tmp_path / "a.sqlite",
        risk=RiskLimits(),
    )
    store = AnalyticsStore(cfg.analytics_db_path)
    loop = ResearchLoop(cfg, store)
    fake_papers = [
        PaperHit("1", "Momentum alpha", "Abstract", "https://x", 2021, 50),
    ]
    with patch("aoa.research.loop.search_papers", return_value=fake_papers):
        created = loop.run_discover()
    assert len(created) == 1
    assert store.list_research_proposals(status="pending")
    assert store.list_approvals(status="pending")
    store.close()
