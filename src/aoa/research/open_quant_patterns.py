"""Pure-Python helpers from afidurko/open-quant-live-book (souzatharsis).

Educational / research reference only. Ports ideas from the Risk Parity,
Entropy, and Transfer Entropy chapters — no R/bookdown runtime, no broker
calls, and no live order path. AOA remains the only execution surface.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskParityResult:
    """Equal (or budgeted) risk-contribution portfolio weights."""

    weights: tuple[float, ...]
    risk_contributions: tuple[float, ...]
    volatility: float
    budget: tuple[float, ...]


@dataclass(frozen=True)
class EntropyStats:
    """Discrete Shannon entropy / mutual-information summary."""

    entropy_x: float
    entropy_y: float
    joint_entropy: float
    mutual_information: float
    global_correlation: float
    bins: int


@dataclass(frozen=True)
class GrangerResult:
    """Linear Granger causality via VAR residual variances (Gaussian TE link)."""

    gc: float
    transfer_entropy: float
    var_restricted: float
    var_unrestricted: float
    lags: int
    n_obs: int


@dataclass(frozen=True)
class NetFlow:
    """Dominant direction of information flow between two series."""

    te_xy: float
    te_yx: float
    net_xy: float
    dominant: str  # "x->y" | "y->x" | "none"


def _validate_cov(cov: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(cov)
    if n < 1:
        raise ValueError("covariance matrix must be non-empty")
    out: list[list[float]] = []
    for i, row in enumerate(cov):
        if len(row) != n:
            raise ValueError("covariance matrix must be square")
        out.append([float(v) for v in row])
        if out[i][i] < 0:
            raise ValueError("diagonal variances must be non-negative")
    return out


def _mat_vec(cov: Sequence[Sequence[float]], w: Sequence[float]) -> list[float]:
    n = len(w)
    return [sum(cov[i][j] * w[j] for j in range(n)) for i in range(n)]


def _portfolio_vol(cov: Sequence[Sequence[float]], w: Sequence[float]) -> float:
    sigma_w = _mat_vec(cov, w)
    var = sum(w[i] * sigma_w[i] for i in range(len(w)))
    return math.sqrt(max(var, 0.0))


def risk_contributions(
    cov: Sequence[Sequence[float]],
    weights: Sequence[float],
) -> tuple[float, ...]:
    """Marginal risk contributions ``w_i (Σw)_i`` (absolute, not normalized)."""
    sigma = _validate_cov(cov)
    if len(weights) != len(sigma):
        raise ValueError("weights length must match covariance dimension")
    sigma_w = _mat_vec(sigma, weights)
    return tuple(weights[i] * sigma_w[i] for i in range(len(weights)))


def inverse_vol_weights(volatilities: Sequence[float]) -> tuple[float, ...]:
    """Naive risk-parity: ``w_i ∝ 1/σ_i`` (normalized to sum 1)."""
    if not volatilities:
        raise ValueError("volatilities must be non-empty")
    inv: list[float] = []
    for v in volatilities:
        if v <= 0:
            raise ValueError("volatilities must be positive")
        inv.append(1.0 / float(v))
    total = sum(inv)
    return tuple(x / total for x in inv)


def equal_risk_contribution(
    cov: Sequence[Sequence[float]],
    *,
    budget: Sequence[float] | None = None,
    max_iter: int = 500,
    tol: float = 1e-12,
    damp: float = 0.5,
) -> RiskParityResult:
    """Risk-budget / ERC weights via damped multiplicative updates (book RiskParity).

    Solves ``w_i (Σw)_i = b_i · wᵀΣw`` with ``sum(b)=1``, ``b≥0``. Default
    ``b = 1/n`` is classic equal risk contribution. Initializes near
    ``w_i ∝ √b_i / σ_i`` and damps the classic ``w ← w · (b V / RC)`` step so
    the fixed-point does not oscillate on diagonal covariances.
    """
    sigma = _validate_cov(cov)
    n = len(sigma)
    if budget is None:
        b = [1.0 / n] * n
    else:
        if len(budget) != n:
            raise ValueError("budget length must match covariance dimension")
        b = [float(x) for x in budget]
        if any(x < 0 for x in b):
            raise ValueError("budget entries must be non-negative")
        s = sum(b)
        if s <= 0:
            raise ValueError("budget must sum to a positive value")
        b = [x / s for x in b]

    if not (0.0 < damp <= 1.0):
        raise ValueError("damp must be in (0, 1]")

    # Diagonal-aware start: w_i ∝ √b_i / σ_i (exact ERC when Σ is diagonal).
    raw = []
    for i in range(n):
        vol = math.sqrt(max(sigma[i][i], 1e-18))
        raw.append(math.sqrt(max(b[i], 0.0)) / vol)
    s0 = sum(raw)
    w = [x / s0 for x in raw] if s0 > 0 else [1.0 / n] * n

    for _ in range(max_iter):
        rc = risk_contributions(sigma, w)
        port_var = sum(rc)
        if port_var <= 0:
            break
        cand: list[float] = []
        for i in range(n):
            if rc[i] <= 0:
                cand.append(0.0)
            else:
                cand.append(w[i] * (b[i] * port_var / rc[i]))
        s = sum(cand)
        if s <= 0:
            break
        cand = [x / s for x in cand]
        blended = [(1.0 - damp) * w[i] + damp * cand[i] for i in range(n)]
        s_b = sum(blended)
        if s_b <= 0:
            break
        new_w = [x / s_b for x in blended]
        delta = sum(abs(new_w[i] - w[i]) for i in range(n))
        w = new_w
        if delta < tol:
            break

    rc = risk_contributions(sigma, w)
    vol = _portfolio_vol(sigma, w)
    return RiskParityResult(
        weights=tuple(w),
        risk_contributions=rc,
        volatility=vol,
        budget=tuple(b),
    )


def _histogram_counts(values: Sequence[float], bins: int) -> list[int]:
    if bins < 2:
        raise ValueError("bins must be >= 2")
    if not values:
        raise ValueError("values must be non-empty")
    lo = min(values)
    hi = max(values)
    if hi == lo:
        counts = [0] * bins
        counts[0] = len(values)
        return counts
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = int((v - lo) / width)
        if idx >= bins:
            idx = bins - 1
        if idx < 0:
            idx = 0
        counts[idx] += 1
    return counts


def _joint_counts(
    xs: Sequence[float],
    ys: Sequence[float],
    bins: int,
) -> tuple[list[int], list[int], list[list[int]]]:
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have the same length")
    if not xs:
        raise ValueError("series must be non-empty")
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_width = (x_hi - x_lo) / bins if x_hi != x_lo else 1.0
    y_width = (y_hi - y_lo) / bins if y_hi != y_lo else 1.0
    cx = [0] * bins
    cy = [0] * bins
    joint = [[0] * bins for _ in range(bins)]
    for x, y in zip(xs, ys, strict=True):
        ix = 0 if x_hi == x_lo else min(bins - 1, max(0, int((x - x_lo) / x_width)))
        iy = 0 if y_hi == y_lo else min(bins - 1, max(0, int((y - y_lo) / y_width)))
        cx[ix] += 1
        cy[iy] += 1
        joint[ix][iy] += 1
    return cx, cy, joint


def shannon_entropy(values: Sequence[float], *, bins: int = 10) -> float:
    """Discrete Shannon entropy (nats) from equal-width binning."""
    counts = _histogram_counts(values, bins)
    n = sum(counts)
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / n
        h -= p * math.log(p)
    return h


def mutual_information_stats(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    bins: int = 10,
) -> EntropyStats:
    """Joint entropy, MI, and normalized global correlation ``λ`` (Entropy ch.).

    ``λ = sqrt(1 - exp(-2 I(X,Y)))`` maps mutual information onto a correlation-like
    ``[0, 1]`` scale (book cites Granger / Lin).
    """
    cx, cy, joint = _joint_counts(xs, ys, bins)
    n = len(xs)
    hx = 0.0
    hy = 0.0
    for c in cx:
        if c > 0:
            p = c / n
            hx -= p * math.log(p)
    for c in cy:
        if c > 0:
            p = c / n
            hy -= p * math.log(p)
    hxy = 0.0
    mi = 0.0
    for i in range(bins):
        for j in range(bins):
            c = joint[i][j]
            if c <= 0:
                continue
            pxy = c / n
            hxy -= pxy * math.log(pxy)
            px = cx[i] / n
            py = cy[j] / n
            mi += pxy * math.log(pxy / (px * py))
    # Numerical guard: MI can be slightly negative from binning noise
    mi = max(0.0, mi)
    lam = math.sqrt(max(0.0, 1.0 - math.exp(-2.0 * mi)))
    return EntropyStats(
        entropy_x=hx,
        entropy_y=hy,
        joint_entropy=hxy,
        mutual_information=mi,
        global_correlation=lam,
        bins=bins,
    )


def _ols_coefficients(design: Sequence[Sequence[float]], y: Sequence[float]) -> list[float]:
    """Solve ordinary least squares via normal equations (Gaussian elimination)."""
    n_obs = len(y)
    if n_obs == 0:
        raise ValueError("empty regression")
    k = len(design[0])
    # XtX and XtY
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for row, yi in zip(design, y, strict=True):
        for i in range(k):
            xty[i] += row[i] * yi
            for j in range(k):
                xtx[i][j] += row[i] * row[j]
    # Augment
    aug = [xtx[i][:] + [xty[i]] for i in range(k)]
    for col in range(k):
        pivot = col
        for r in range(col + 1, k):
            if abs(aug[r][col]) > abs(aug[pivot][col]):
                pivot = r
        aug[col], aug[pivot] = aug[pivot], aug[col]
        diag = aug[col][col]
        if abs(diag) < 1e-15:
            # Singular — fall back to zeros for this column
            continue
        for j in range(col, k + 1):
            aug[col][j] /= diag
        for r in range(k):
            if r == col:
                continue
            factor = aug[r][col]
            for j in range(col, k + 1):
                aug[r][j] -= factor * aug[col][j]
    return [aug[i][k] for i in range(k)]


def _residual_variance(design: Sequence[Sequence[float]], y: Sequence[float]) -> float:
    beta = _ols_coefficients(design, y)
    sse = 0.0
    for row, yi in zip(design, y, strict=True):
        pred = sum(b * x for b, x in zip(beta, row, strict=True))
        err = yi - pred
        sse += err * err
    return sse / len(y)


def linear_granger_causality(
    cause: Sequence[float],
    effect: Sequence[float],
    *,
    lags: int = 1,
) -> GrangerResult:
    """Linear Granger causality GC = log(var_R / var_U); TE ≈ GC/2 (Gaussian).

    Restricted model: ``Y_t ~ Y lags``. Unrestricted: ``Y_t ~ Y lags + X lags``.
    Matches the Transfer Entropy chapter VAR formulation and the
    Barnett–Barrett–Seth Gaussian equivalence ``TE = GC/2``.
    """
    if lags < 1:
        raise ValueError("lags must be >= 1")
    if len(cause) != len(effect):
        raise ValueError("cause and effect must have the same length")
    n = len(effect)
    if n <= lags + 1:
        raise ValueError("series too short for requested lags")

    y: list[float] = []
    design_r: list[list[float]] = []
    design_u: list[list[float]] = []
    for t in range(lags, n):
        y.append(float(effect[t]))
        row_r = [1.0]
        row_u = [1.0]
        for lag in range(1, lags + 1):
            row_r.append(float(effect[t - lag]))
            row_u.append(float(effect[t - lag]))
        for lag in range(1, lags + 1):
            row_u.append(float(cause[t - lag]))
        design_r.append(row_r)
        design_u.append(row_u)

    var_r = _residual_variance(design_r, y)
    var_u = _residual_variance(design_u, y)
    # Guard against zero / tiny unrestricted variance
    var_r = max(var_r, 1e-18)
    var_u = max(var_u, 1e-18)
    gc = math.log(var_r / var_u)
    if gc < 0:
        gc = 0.0
    return GrangerResult(
        gc=gc,
        transfer_entropy=gc / 2.0,
        var_restricted=var_r,
        var_unrestricted=var_u,
        lags=lags,
        n_obs=len(y),
    )


def net_information_flow(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    lags: int = 1,
) -> NetFlow:
    """Net TÊ_{X→Y} = TE_{X→Y} − TE_{Y→X} (dominant predictive direction)."""
    xy = linear_granger_causality(xs, ys, lags=lags)
    yx = linear_granger_causality(ys, xs, lags=lags)
    net = xy.transfer_entropy - yx.transfer_entropy
    if abs(net) < 1e-12:
        dominant = "none"
    elif net > 0:
        dominant = "x->y"
    else:
        dominant = "y->x"
    return NetFlow(
        te_xy=xy.transfer_entropy,
        te_yx=yx.transfer_entropy,
        net_xy=net,
        dominant=dominant,
    )


def cov_from_returns(returns: Sequence[Sequence[float]]) -> list[list[float]]:
    """Sample covariance of aligned return series (rows = assets, cols = time)."""
    if not returns:
        raise ValueError("returns must be non-empty")
    n = len(returns)
    t = len(returns[0])
    if t < 2:
        raise ValueError("need at least 2 observations")
    for row in returns:
        if len(row) != t:
            raise ValueError("all return series must share the same length")
    means = [sum(row) / t for row in returns]
    cov = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            s = 0.0
            for k in range(t):
                s += (returns[i][k] - means[i]) * (returns[j][k] - means[j])
            cov[i][j] = s / (t - 1)
    return cov


def synthetic_smoke(*, seed: int = 7) -> dict[str, object]:
    """Offline smoke for ``aoa openquant smoke`` — no broker, no orders."""
    # Deterministic toy system from the Transfer Entropy chapter:
    # x1[t] = 0.441 x1[t-1] + e1; x2[t] = 0.51 x1[t-1]^2 + e2 (linearized here).
    _ = seed
    n = 200
    x1 = [0.0] * n
    x2 = [0.0] * n
    # Use a fixed LCG so smoke is seed-stable without importing random.
    state = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    for i in range(1, n):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        e1 = (state / 0x7FFFFFFF) * 2.0 - 1.0
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        e2 = (state / 0x7FFFFFFF) * 2.0 - 1.0
        x1[i] = 0.441 * x1[i - 1] + e1
        x2[i] = 0.51 * x1[i - 1] + e2  # linear coupling for GC smoke

    flow = net_information_flow(x1, x2, lags=1)
    mi = mutual_information_stats(x1, x2, bins=8)

    # Two-asset ERC: asset 0 twice as volatile as asset 1
    vols = (0.20, 0.10)
    inv = inverse_vol_weights(vols)
    cov = [[0.04, 0.0], [0.0, 0.01]]
    erc = equal_risk_contribution(cov)

    ok = (
        flow.dominant == "x->y"
        and mi.mutual_information >= 0.0
        and abs(sum(erc.weights) - 1.0) < 1e-8
        and abs(inv[0] - 1.0 / 3.0) < 1e-8
    )
    return {
        "ok": ok,
        "net_flow": {
            "te_xy": flow.te_xy,
            "te_yx": flow.te_yx,
            "net_xy": flow.net_xy,
            "dominant": flow.dominant,
        },
        "mutual_information": mi.mutual_information,
        "global_correlation": mi.global_correlation,
        "inverse_vol_weights": list(inv),
        "erc_weights": list(erc.weights),
        "never_live": True,
        "module": "aoa.research.open_quant_patterns",
        "companion": "open-quant-live-book",
    }


__all__ = [
    "EntropyStats",
    "GrangerResult",
    "NetFlow",
    "RiskParityResult",
    "cov_from_returns",
    "equal_risk_contribution",
    "inverse_vol_weights",
    "linear_granger_causality",
    "mutual_information_stats",
    "net_information_flow",
    "risk_contributions",
    "shannon_entropy",
    "synthetic_smoke",
]
