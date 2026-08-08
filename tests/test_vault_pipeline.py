"""Tests for vault pipeline integration."""

from __future__ import annotations

from aoa.loop.prompts import load_tasks
from aoa.swarm.stages import VaultSyncStage
from aoa.swarm.stages import default_stages as swarm_stages
from aoa.workloop.models import STAGE_ORDER
from aoa.workloop.stages import VaultSyncStage as WorkloopVaultSyncStage
from aoa.workloop.stages import default_stages as workloop_stages


def test_swarm_pipeline_includes_vault_sync():
    names = [s.name for s in swarm_stages()]
    assert names[-1] == "vault_sync"
    assert isinstance(swarm_stages()[-1], VaultSyncStage)


def test_workloop_pipeline_includes_vault_sync():
    names = [s.name for s in workloop_stages()]
    assert names == list(STAGE_ORDER)
    assert "vault_sync" in names
    idx = names.index("vault_sync")
    assert names[idx - 1] == "adapt"
    assert names[idx + 1] == "propose"
    assert isinstance(workloop_stages()[idx], WorkloopVaultSyncStage)


def test_tier1_includes_vault_sync_step():
    tasks = load_tasks()
    tier1 = tasks["tier1"]
    assert "vault-sync" in tier1.steps
    assert tier1.steps.index("vault-sync") > tier1.steps.index("repair-triage")
    assert tier1.steps.index("vault-sync") < tier1.steps.index("verify-quick")
