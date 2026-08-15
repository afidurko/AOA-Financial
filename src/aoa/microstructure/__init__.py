"""Offline microstructure workspace mesh for AOA Financial.

Aggregates companion HFT / LOB research lanes into one status surface.
Individual CLIs remain: ``aoa avellaneda``, ``aoa visualhft``, ``aoa hft``.
"""

from __future__ import annotations

from aoa.microstructure.catalog import LANES, catalog_status

__all__ = ["LANES", "catalog_status"]
