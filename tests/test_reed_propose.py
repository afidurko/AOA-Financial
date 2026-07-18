"""Reed task factory normalizes repair item_id / escalation."""

from __future__ import annotations

from aoa.team.reed import ReedAgent


class _Null:
    def structured(self, *args, **kwargs):
        raise RuntimeError("unused")


def test_reed_uses_item_id_and_severity():
    reed = ReedAgent(_Null())
    out = reed.propose_tasks(
        repair_items=[
            {
                "item_id": "r1",
                "title": "Ruff check failed",
                "severity": "critical",
                "fixable": True,
                "requires_escalation": False,
                "detail": "F401",
            },
            {
                "item_id": "r2",
                "title": "Rotate keys",
                "severity": "critical",
                "fixable": True,
                "requires_escalation": True,
            },
        ],
        backlog_items=[
            {"id": "upg-1", "title": "Doc", "automatable": True, "detail": "x"},
        ],
    )
    by_id = {t["id"]: t for t in out["tasks"]}
    assert by_id["repair-r1"]["automatable"] is True
    assert by_id["repair-r1"]["priority"] == "critical"
    assert by_id["repair-r1"]["item_id"] == "r1"
    assert by_id["repair-r2"]["automatable"] is False
    assert by_id["upg-1"]["automatable"] is True
    # Need-order: automatable repair before backlog
    assert out["tasks"][0]["id"] == "repair-r1"
