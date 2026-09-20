"""Integrity Ten — cohesive integrity mesh for AOA-Financial.

Ten ATTL members (excluding Tom & Morgan market lanes) continuously check
code, workspaces, neural memory, and mesh cohesion. When issues arise they
prepare a corrective action and notify the user; implant happens only after
``aoa integrity approve``.
"""

from aoa.integrity.roster import INTEGRITY_TEN, integrity_names, integrity_pairs
from aoa.integrity.squad import IntegrityCycleResult, IntegritySquad

__all__ = [
    "INTEGRITY_TEN",
    "IntegrityCycleResult",
    "IntegritySquad",
    "integrity_names",
    "integrity_pairs",
]
