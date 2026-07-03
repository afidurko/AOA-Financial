"""Low-Rank Adaptation (LoRA) toolkit for the swarm and beyond.

Two layers, sharing the same low-rank idea (ΔW = (α/r)·A·B):

* :mod:`aoa.adapt.lowrank` — a dependency-free low-rank adapter (pure Python),
  used by the swarm to recalibrate agent signals online.
* :mod:`aoa.adapt.signal_adapter` — :class:`SignalAdapter`, the trading-signal
  application of the above (learns conviction corrections from realized PnL).
* :mod:`aoa.adapt.torch_lora` — an optional, reusable PyTorch ``LoRALinear`` for
  general neural-net fine-tuning in *other* projects (requires ``torch``).
"""

from __future__ import annotations

from aoa.adapt.lowrank import LowRankAdapter
from aoa.adapt.signal_adapter import SignalAdapter

__all__ = ["LowRankAdapter", "SignalAdapter"]
