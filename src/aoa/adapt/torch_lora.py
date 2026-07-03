"""PyTorch Low-Rank Adaptation (LoRA) primitives — optional, reusable.

This is a small, dependency-light, *framework* implementation of LoRA that
other projects can import directly, independent of the trading swarm:

    from aoa.adapt.torch_lora import (
        LoRALinear, mark_only_lora_as_trainable,
        save_lora_adapter, load_lora_adapter,
    )

    base = nn.Linear(768, 768)
    layer = LoRALinear.from_linear(base, rank=8, alpha=16, dropout=0.05)
    y = layer(x)                 # base(x) + (alpha/r) · B·A·x
    layer.merge()                # fold the delta into the frozen weight for fast inference
    layer.unmerge()              # restore the separable form for further training

    mark_only_lora_as_trainable(model)        # freeze everything but the adapters
    save_lora_adapter(model, "adapter.pt")    # persist only the LoRA params (tiny)
    load_lora_adapter(model, "adapter.pt")

``torch`` is an *optional* dependency: importing this module without torch
installed raises a friendly error, and the rest of ``aoa`` never imports it, so
the swarm keeps running torch-free. Install with ``pip install "aoa-financial[torch]"``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

try:  # torch is optional — only needed for this module.
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - exercised only when torch is absent
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover
    import torch
    from torch import nn


class _TorchUnavailable(RuntimeError):
    pass


def _require_torch() -> None:
    if torch is None:  # pragma: no cover - trivial guard
        raise _TorchUnavailable(
            "PyTorch is required for aoa.adapt.torch_lora. "
            'Install it with: pip install "aoa-financial[torch]"'
        )


def __getattr__(name: str):
    # Define the torch-dependent symbols lazily so that *importing* the module
    # without torch does not blow up; only *using* it does.
    if name in {
        "LoRALinear",
        "mark_only_lora_as_trainable",
        "lora_state_dict",
        "save_lora_adapter",
        "load_lora_adapter",
    }:
        _require_torch()
        _build_api()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _build_api() -> None:
    """Populate the module namespace with the torch-backed implementations.

    Called lazily on first access so the module is importable without torch.
    """
    if "LoRALinear" in globals():  # already built
        return

    class LoRALinear(nn.Module):  # type: ignore[misc]
        """A ``nn.Linear`` augmented with a trainable low-rank adapter.

        The base weight (and bias) are frozen; only ``lora_A`` and ``lora_B``
        receive gradients. ``lora_A`` is kaiming-initialized and ``lora_B`` is
        zero so the adapter starts as a no-op.
        """

        def __init__(
            self,
            in_features: int,
            out_features: int,
            *,
            rank: int = 8,
            alpha: float = 16.0,
            dropout: float = 0.0,
            bias: bool = True,
        ) -> None:
            super().__init__()
            if rank <= 0:
                raise ValueError("rank must be a positive integer")
            self.in_features = in_features
            self.out_features = out_features
            self.rank = rank
            self.alpha = float(alpha)
            self.scaling = self.alpha / rank
            self.merged = False

            self.weight = nn.Parameter(
                torch.empty(out_features, in_features), requires_grad=False
            )
            nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
            if bias:
                self.bias = nn.Parameter(
                    torch.zeros(out_features), requires_grad=False
                )
            else:
                self.register_parameter("bias", None)

            self.lora_A = nn.Parameter(torch.empty(rank, in_features))
            self.lora_B = nn.Parameter(torch.zeros(out_features, rank))
            nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

        @classmethod
        def from_linear(
            cls,
            linear: nn.Linear,
            *,
            rank: int = 8,
            alpha: float = 16.0,
            dropout: float = 0.0,
        ) -> LoRALinear:
            """Wrap an existing ``nn.Linear``, copying and freezing its weights."""
            layer = cls(
                linear.in_features,
                linear.out_features,
                rank=rank,
                alpha=alpha,
                dropout=dropout,
                bias=linear.bias is not None,
            )
            with torch.no_grad():
                layer.weight.copy_(linear.weight)
                if linear.bias is not None:
                    layer.bias.copy_(linear.bias)
            return layer

        def _delta_weight(self) -> torch.Tensor:
            return self.scaling * (self.lora_B @ self.lora_A)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            from torch.nn import functional as F

            if self.merged:
                return F.linear(x, self.weight, self.bias)
            base = F.linear(x, self.weight, self.bias)
            delta = F.linear(self.dropout(x), self._delta_weight())
            return base + delta

        @torch.no_grad()
        def merge(self) -> None:
            """Fold the low-rank delta into ``weight`` for fast inference."""
            if not self.merged:
                self.weight += self._delta_weight()
                self.merged = True

        @torch.no_grad()
        def unmerge(self) -> None:
            """Undo :meth:`merge`, restoring the separable training form."""
            if self.merged:
                self.weight -= self._delta_weight()
                self.merged = False

        def extra_repr(self) -> str:
            return (
                f"in_features={self.in_features}, out_features={self.out_features}, "
                f"rank={self.rank}, alpha={self.alpha}, merged={self.merged}"
            )

    def mark_only_lora_as_trainable(model: nn.Module) -> None:
        """Freeze every parameter except those named ``lora_*``."""
        for name, param in model.named_parameters():
            param.requires_grad = "lora_" in name

    def lora_state_dict(model: nn.Module) -> dict:
        """Return only the LoRA parameters from ``model`` — a tiny checkpoint."""
        return {
            name: param.detach().cpu()
            for name, param in model.state_dict().items()
            if "lora_" in name
        }

    def save_lora_adapter(model: nn.Module, path: str) -> None:
        torch.save(lora_state_dict(model), path)

    def load_lora_adapter(
        model: nn.Module, path: str, *, strict: bool = False
    ) -> None:
        state = torch.load(path, map_location="cpu")
        model.load_state_dict(state, strict=strict)

    globals().update(
        LoRALinear=LoRALinear,
        mark_only_lora_as_trainable=mark_only_lora_as_trainable,
        lora_state_dict=lora_state_dict,
        save_lora_adapter=save_lora_adapter,
        load_lora_adapter=load_lora_adapter,
    )


# Public API (all built lazily by ``_build_api`` and resolved via ``__getattr__``
# so the module stays importable without torch):
#   LoRALinear, mark_only_lora_as_trainable, lora_state_dict,
#   save_lora_adapter, load_lora_adapter
