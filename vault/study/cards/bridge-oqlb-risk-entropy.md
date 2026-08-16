---
type: study-card
card_id: bridge-oqlb-risk-entropy
field: bridge
title: Risk parity ↔ information flow
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Risk parity ↔ information flow

**Field:** `bridge` · **id:** `bridge-oqlb-risk-entropy`

## Statement

Equal risk contribution sets ``w_i (Σw)_i`` equal across assets (or to a risk
budget ``b``), while mutual information / transfer entropy quantify nonlinear and
directional dependence between return series. Together they are portfolio-design
and causality diagnostics — not an AOA execution stage.

## Proof sketch

1) Risk parity: ``w_i ∂f/∂w_i`` equal for homogeneous risk ``f(w)=√(wᵀΣw)``.
2) Shannon MI ``I(X;Y)`` and ``λ=√(1−e^{−2I})`` map dependence onto a correlation-like scale.
3) For jointly Gaussian processes, transfer entropy equals half linear Granger causality.
4) Net flow ``TE_{X→Y}−TE_{Y→X}`` picks the dominant predictive direction.

## Applications

- Offline portfolio risk-budget research beside Andrea / FinancePy context
- Julie algorithm clarity for econophysics / portfolio study cards

## AOA mesh

Research helpers in `aoa.research.open_quant_patterns` never call a broker;
sibling afidurko/open-quant-live-book is reference-only — never an AOA order path.

## Bridges

bridge-sdf-martingale, bridge-free-energy

## Drill

Define ERC weights from Σ and state the Gaussian link between Granger causality and transfer entropy.
