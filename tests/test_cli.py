"""Tests for CLI exit-code behavior."""

from __future__ import annotations

from aoa.cli import _cycle_exit_code
from aoa.execution.executor import ExecutionReport
from aoa.swarm.blackboard import Blackboard
from aoa.swarm.orchestrator import CycleResult


def test_cycle_exit_code_zero_on_success():
    result = CycleResult(
        blackboard=Blackboard(),
        execution=ExecutionReport(submitted=[object()], errors=[]),
    )
    assert _cycle_exit_code(result) == 0


def test_cycle_exit_code_one_on_execution_errors():
    result = CycleResult(
        blackboard=Blackboard(),
        execution=ExecutionReport(errors=[{"symbol": "AAPL", "error": "rejected"}]),
    )
    assert _cycle_exit_code(result) == 1
