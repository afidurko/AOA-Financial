"""Tests for loop prompt shortkeys and task runners."""

from __future__ import annotations

from aoa.loop.prompts import (
    format_automations,
    get_prompt,
    list_automation_prompts,
    list_prompt_keys,
    load_tasks,
    run_task,
)
from aoa.repair.schedule_gate import GateAction


def test_prompt_shortkeys_load():
    keys = list_prompt_keys()
    assert "L1" in keys
    assert "L2" in keys
    assert "GATE-A" in keys


def test_automation_prompts_are_the_three_scheduled_ones():
    keys = {p.key for p in list_automation_prompts()}
    assert keys == {"L1", "L2", "BRIEF"}
    for prompt in list_automation_prompts():
        assert prompt.branch == "main"
        assert prompt.automation


def test_format_automations_renders_all_three():
    rendered = format_automations()
    assert "AOA daily triage" in rendered
    assert "AOA fable repair L2" in rendered
    assert "AOA user brief" in rendered
    assert "Branch: main" in rendered
    assert "loop brief --push" in rendered


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
