"""Neuroplasticity-inspired learning from the append-only journal.

Each cycle can read distilled lessons from past decisions and write back
consolidated memory after execution — closing the log → memory → behavior loop.
"""

from aoa.plasticity.store import PlasticityStore

__all__ = ["PlasticityStore"]
