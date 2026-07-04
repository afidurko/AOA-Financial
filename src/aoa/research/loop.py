"""Research proposal loop — literature → backtest hint → user approval inbox."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from aoa.research.scholar import PaperHit, ScholarSearchError, extract_technique_hint, search_papers

if TYPE_CHECKING:
    from aoa.analytics.store import AnalyticsStore
    from aoa.config import Config


class ResearchLoop:
    """Discover papers and queue algorithm edge proposals for human approval."""

    def __init__(self, config: Config, store: AnalyticsStore) -> None:
        self.config = config
        self.store = store

    def run_discover(self) -> list[dict[str, Any]]:
        if not self.config.scholar_enabled:
            return []
        try:
            papers = search_papers(
                self.config.scholar_query,
                limit=self.config.scholar_max_results,
            )
        except ScholarSearchError:
            return []

        created: list[dict[str, Any]] = []
        for paper in papers:
            proposal = self._create_proposal(paper)
            if proposal:
                created.append(proposal)
        return created

    def _create_proposal(self, paper: PaperHit) -> dict[str, Any] | None:
        technique = extract_technique_hint(paper)
        score = _heuristic_backtest_score(paper)
        pid = str(uuid.uuid4())
        self.store.add_research_proposal(
            title=paper.title,
            abstract=paper.abstract[:500],
            source="semantic_scholar",
            source_url=paper.url,
            technique=technique,
            backtest_score=score,
            payload=paper.to_context(),
            proposal_id=pid,
        )
        approval_id = self.store.add_approval(
            kind="research",
            title=f"Research edge: {technique}",
            summary=paper.title,
            payload={"research_id": pid, "technique": technique, "score": score},
            proposal_id=pid,
        )
        return {
            "research_id": pid,
            "approval_id": approval_id,
            "title": paper.title,
            "technique": technique,
            "backtest_score": score,
            "url": paper.url,
        }


def _heuristic_backtest_score(paper: PaperHit) -> float:
    """Proxy score from citations + recency — not a real backtest (human gate follows)."""
    citations = min(paper.citation_count, 500) / 500.0
    recency = 0.5
    if paper.year:
        recency = max(0.0, min(1.0, (paper.year - 2010) / 15.0))
    return round(0.6 * citations + 0.4 * recency, 3)
