"""Tests for the loop-aware user brief (Alex + STATE.md + repair queue)."""

from __future__ import annotations

import json

from aoa.analytics.store import AnalyticsStore
from aoa.loop.user_brief import (
    build_loop_user_brief,
    parse_state_md,
    repair_queue_summary,
)
from aoa.team.alex import AlexAgent
from aoa.team.models import PriorityLevel

_STATE_MD = """# Loop State — AOA-Financial

Last run: 2026-07-07 23:49 UTC

## High Priority (loop is acting or waiting on human)

- **Rotate exposed API keys** — revoke and regenerate in each console.

## Watch List

- **Moomoo OpenD offline** — OpenD not running at 127.0.0.1:11111.
- **_none_** — placeholder should be ignored.

## Repair queue

Machine-readable queue: data/{AOA_ENV}/repair/queue.json
"""


def test_parse_state_md(tmp_path):
    state = tmp_path / "STATE.md"
    state.write_text(_STATE_MD, encoding="utf-8")
    summary = parse_state_md(state)
    assert len(summary.high_priority) == 1
    assert summary.high_priority[0]["title"] == "Rotate exposed API keys"
    assert len(summary.watch) == 1
    assert summary.watch[0]["title"] == "Moomoo OpenD offline"


def test_parse_state_md_missing_file(tmp_path):
    summary = parse_state_md(tmp_path / "nope.md")
    assert summary.is_empty


def test_repair_queue_summary(tmp_path):
    repair_dir = tmp_path / "repair"
    repair_dir.mkdir()
    (repair_dir / "queue.json").write_text(
        json.dumps(
            {"items": [{"fixable": True}, {"fixable": False}, {"fixable": True}]}
        ),
        encoding="utf-8",
    )
    summary = repair_queue_summary(repair_dir)
    assert summary == {"count": 3, "fixable": 2}


def test_repair_queue_summary_no_file(tmp_path):
    assert repair_queue_summary(tmp_path) == {"count": 0, "fixable": 0}


def test_alex_reads_loop_state(tmp_path, fake_llm):
    state = tmp_path / "STATE.md"
    state.write_text(_STATE_MD, encoding="utf-8")
    agent = AlexAgent(fake_llm)
    brief = agent.prioritize(market_open=True, loop_state_path=state)
    titles = [i.title for i in brief.must_do]
    assert "Rotate exposed API keys" in titles
    assert any(i.level is PriorityLevel.SHOULD for i in brief.should_do)


def test_build_loop_user_brief_attaches_replies(tmp_path, fake_llm):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    nid = store.log_notification(
        kind="escalation", title="Confirm rotation", message="Rotate keys?"
    )
    store.mark_awaiting_response(nid)
    pending = store.list_pending_responses()
    assistant = AlexAgent(fake_llm).prioritize(market_open=True)
    brief = build_loop_user_brief(
        assistant_brief=assistant,
        repair_summary={"count": 2, "fixable": 1},
        pending_responses=pending,
    )
    assert brief.repair_queue == {"count": 2, "fixable": 1}
    actions = {r.action for r in brief.suggested_replies}
    assert actions == {"approve", "reject"}
    assert "fixable repair item" in brief.summary
    store.close()
