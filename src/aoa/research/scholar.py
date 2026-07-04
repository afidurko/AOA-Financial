"""Literature search via Semantic Scholar (Google Scholar has no public API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"


@dataclass(frozen=True)
class PaperHit:
    paper_id: str
    title: str
    abstract: str
    url: str
    year: int | None
    citation_count: int

    def to_context(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "url": self.url,
            "year": self.year,
            "citation_count": self.citation_count,
        }


class ScholarSearchError(RuntimeError):
    pass


def search_papers(
    query: str,
    *,
    limit: int = 5,
    timeout: float = 20.0,
) -> list[PaperHit]:
    """Search academic papers relevant to trading algorithm research."""
    q = query.strip()
    if not q:
        return []
    params = {
        "query": q,
        "limit": max(1, min(limit, 20)),
        "fields": "title,abstract,url,year,citationCount,paperId",
    }
    try:
        resp = httpx.get(_SCHOLAR_API, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ScholarSearchError(f"Semantic Scholar search failed: {exc}") from exc

    hits: list[PaperHit] = []
    for row in data.get("data") or []:
        hits.append(
            PaperHit(
                paper_id=str(row.get("paperId") or ""),
                title=str(row.get("title") or "Untitled"),
                abstract=str(row.get("abstract") or "")[:2000],
                url=str(row.get("url") or ""),
                year=row.get("year"),
                citation_count=int(row.get("citationCount") or 0),
            )
        )
    return hits


def extract_technique_hint(paper: PaperHit) -> str:
    """Heuristic technique label from title/abstract (for proposal cards)."""
    text = f"{paper.title} {paper.abstract}".lower()
    keywords = (
        ("momentum", "momentum factor"),
        ("mean reversion", "mean reversion"),
        ("volatility", "volatility scaling"),
        ("portfolio", "portfolio optimization"),
        ("machine learning", "ML signal"),
        ("reinforcement", "RL policy"),
        ("options", "options structure"),
        ("sentiment", "sentiment overlay"),
    )
    for needle, label in keywords:
        if needle in text:
            return label
    return "quantitative signal"
