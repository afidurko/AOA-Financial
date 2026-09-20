"""Tests for the shared fan-out primitive and thread-safe journal."""

from __future__ import annotations

import threading
import time

import pytest

from aoa.journal.store import Journal
from aoa.parallel import fan_out, fan_out_named


def test_fan_out_preserves_order_when_parallel():
    def slow_square(x: int) -> int:
        time.sleep(0.01 * (5 - x))  # later items finish first
        return x * x

    assert fan_out(slow_square, [1, 2, 3, 4], workers=4) == [1, 4, 9, 16]


def test_fan_out_runs_inline_for_single_item_or_single_worker():
    seen: list[str] = []

    def record(x: int) -> int:
        seen.append(threading.current_thread().name)
        return x

    main = threading.current_thread().name
    assert fan_out(record, [7], workers=8) == [7]
    assert fan_out(record, [1, 2, 3], workers=1) == [1, 2, 3]
    assert fan_out(record, [1, 2, 3], workers=8, parallel=False) == [1, 2, 3]
    assert set(seen) == {main}


def test_fan_out_empty_and_generator_input():
    assert fan_out(lambda x: x, []) == []
    assert fan_out(lambda x: x + 1, (i for i in range(3)), workers=2) == [1, 2, 3]


def test_fan_out_propagates_exceptions():
    def boom(x: int) -> int:
        if x == 2:
            raise ValueError("two")
        return x

    with pytest.raises(ValueError, match="two"):
        fan_out(boom, [1, 2, 3], workers=3)


def test_fan_out_named_maps_lane_names_to_results():
    out = fan_out_named({"a": lambda: 1, "b": lambda: "two"}, workers=2)
    assert out == {"a": 1, "b": "two"}


def test_journal_concurrent_records_stay_intact(tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    payload = {"blob": "x" * 20_000}

    def write(i: int) -> None:
        journal.record(f"event.{i}", payload)

    fan_out(write, range(32), workers=8)
    rows = journal.read_all()
    assert len(rows) == 32
    assert {r["event"] for r in rows} == {f"event.{i}" for i in range(32)}
    assert all(len(r["blob"]) == 20_000 for r in rows)
