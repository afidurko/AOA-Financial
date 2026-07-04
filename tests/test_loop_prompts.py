"""Tests for loop prompt shortkeys and task runners."""

from __future__ import annotations

from aoa.loop.prompts import get_prompt, list_prompt_keys, load_tasks, run_task
from aoa.repair.schedule_gate import GateAction


def test_prompt_shortkeys_load():
    keys = list_prompt_keys()
    assert "L1" in keys
    assert "L2" in keys
    assert "GATE-A" in keys


def test_get_prompt_l1_body():
    prompt = get_prompt("L1")
    assert prompt is not None
    assert "loop-triage" in prompt.body
    assert "repair gate --for triage" in prompt.body


def test_run_task_tier1_check():
    result = run_task("tier1-check")
    assert result.task == "tier1-check"
    assert result.gate_action in {a.value for a in GateAction}


def test_tasks_yaml_has_expected_loops():
    tasks = load_tasks()
    assert "tier1" in tasks
    assert "tier2-check" in tasks
    assert "gate-triage" in tasks["tier1"].steps
