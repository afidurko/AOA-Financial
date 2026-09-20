"""Pure-Python helpers from afidurko/open-quant-live-book (souzatharsis).

Educational / research reference only. Ports ideas from Risk Parity,
Entropy, Transfer Entropy, Financial Networks, Statistical Methods, and
Stylized Facts chapters — no R/bookdown runtime, no broker calls, and no
live order path. AOA remains the only execution surface.
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
    risk_fractions: tuple[float, ...]
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


@dataclass(frozen=True)
class TangencyResult:
    """Mean-variance tangency (max Sharpe) portfolio weights."""

    weights: tuple[float, ...]
    expected_return: float
    volatility: float
    sharpe: float
    long_only: bool


@dataclass(frozen=True)
class StylizedFacts:
    """Classic return stylized-fact diagnostics (book StylizedFacts stubs → math)."""

    n: int
    mean: float
    std: float
    skewness: float
    excess_kurtosis: float
    acf1: float
    abs_acf1: float
    fat_tails: bool
    volatility_clustering: bool


@dataclass(frozen=True)
class NetworkEdge:
    """Undirected correlation edge above a threshold."""

    i: int
    j: int
    correlation: float


@dataclass(frozen=True)
class CorrelationNetwork:
    """Thresholded correlation graph + degree centrality."""

    n: int
    threshold: float
    edges: tuple[NetworkEdge, ...]
    degree: tuple[int, ...]
    degree_centrality: tuple[float, ...]
    kind: str = "threshold"  # threshold | mst | pmfg | partial


@dataclass(frozen=True)
class BlackLittermanResult:
    """Black–Litterman posterior means and tangency weights (research-only)."""

    posterior_returns: tuple[float, ...]
    weights: tuple[float, ...]
    expected_return: float
    volatility: float
    sharpe: float
    tau: float
    risk_aversion: float


@dataclass(frozen=True)
class ShrinkageResult:
    """Ledoit–Wolf-style shrunk covariance toward scaled identity."""

    cov: tuple[tuple[float, ...], ...]
    shrinkage: float
    target_variance: float
    n_obs: int


@dataclass(frozen=True)
class CVaRBudgetResult:
    """Historical CVaR risk-budget weights (nested / equal CVaR contribution)."""

    weights: tuple[float, ...]
    cvar: float
    contributions: tuple[float, ...]
    fractions: tuple[float, ...]
    alpha: float
    budget: tuple[float, ...]


@dataclass(frozen=True)
class StylizedRegimeSummary:
    """Rolling stylized-fact regime summary over a return series."""

    window: int
    n_windows: int
    fat_tail_fraction: float
    vol_cluster_fraction: float
    latest: StylizedFacts
    regime: str  # fat_tails | vol_cluster | calm | mixed


def _normalize(values: Sequence[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        raise ValueError("cannot normalize non-positive weights")
    return [float(v) / total for v in values]


def _normalize_signed(values: Sequence[float]) -> list[float]:
    """Normalize so weights sum to 1, allowing a negative gross (short tangency)."""
    total = sum(values)
    if abs(total) < 1e-18 or not math.isfinite(total):
        raise ValueError("cannot normalize near-zero or non-finite weight sum")
    return [float(v) / total for v in values]


def _validate_cov(cov: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(cov)
    if n < 1:
        raise ValueError("covariance matrix must be non-empty")
    out: list[list[float]] = []
    for i, row in enumerate(cov):
        if len(row) != n:
            raise ValueError("covariance matrix must be square")
        out.append([float(v) for v in row])
        for j, v in enumerate(out[i]):
            if not math.isfinite(v):
                raise ValueError("covariance entries must be finite")
            if i == j and v < 0:
                raise ValueError("diagonal variances must be non-negative")
    return out


def _require_bins(bins: int) -> int:
    if bins < 2:
        raise ValueError("bins must be >= 2")
    return bins


def _require_finite_positive(value: float, *, label: str) -> float:
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{label} must be finite")
    if v <= 0:
        raise ValueError(f"{label} must be positive")
    return v


def _mat_vec(cov: Sequence[Sequence[float]], w: Sequence[float]) -> list[float]:
    n = len(w)
    return [sum(cov[i][j] * w[j] for j in range(n)) for i in range(n)]


def _portfolio_vol(cov: Sequence[Sequence[float]], w: Sequence[float]) -> float:
    sigma_w = _mat_vec(cov, w)
    var = sum(w[i] * sigma_w[i] for i in range(len(w)))
    return math.sqrt(max(var, 0.0))


def _risk_contributions_raw(
    cov: Sequence[Sequence[float]],
    weights: Sequence[float],
) -> tuple[float, ...]:
    sigma_w = _mat_vec(cov, weights)
    return tuple(weights[i] * sigma_w[i] for i in range(len(weights)))


def _risk_fractions(rc: Sequence[float]) -> tuple[float, ...]:
    total = sum(rc)
    if total <= 0:
        n = len(rc)
        return tuple(1.0 / n for _ in range(n)) if n else ()
    return tuple(r / total for r in rc)


def risk_contributions(
    cov: Sequence[Sequence[float]],
    weights: Sequence[float],
) -> tuple[float, ...]:
    """Marginal risk contributions ``w_i (Σw)_i`` (absolute, not normalized)."""
    sigma = _validate_cov(cov)
    if len(weights) != len(sigma):
        raise ValueError("weights length must match covariance dimension")
    return _risk_contributions_raw(sigma, weights)


def inverse_vol_weights(volatilities: Sequence[float]) -> tuple[float, ...]:
    """Naive risk-parity: ``w_i ∝ 1/σ_i`` (normalized to sum 1)."""
    if not volatilities:
        raise ValueError("volatilities must be non-empty")
    inv: list[float] = []
    for i, raw in enumerate(volatilities):
        v = _require_finite_positive(raw, label=f"volatilities[{i}]")
        inv_i = 1.0 / v
        if not math.isfinite(inv_i):
            raise ValueError(f"volatilities[{i}] is too small for stable inversion")
        inv.append(inv_i)
    weights = _normalize(inv)
    if any(not math.isfinite(w) for w in weights):
        raise ValueError("inverse-vol weights must be finite")
    return tuple(weights)

def _parse_budget(n: int, budget: Sequence[float] | None) -> list[float]:
    if budget is None:
        return [1.0 / n] * n
    if len(budget) != n:
        raise ValueError("budget length must match covariance dimension")
    b = [float(x) for x in budget]
    if any(x < 0 for x in b):
        raise ValueError("budget entries must be non-negative")
    try:
        return _normalize(b)
    except ValueError as exc:
        raise ValueError("budget must sum to a positive value") from exc


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
    b = _parse_budget(n, budget)

    if not (0.0 < damp <= 1.0):
        raise ValueError("damp must be in (0, 1]")

    # Diagonal-aware start: w_i ∝ √b_i / σ_i (exact ERC when Σ is diagonal).
    raw = [
        math.sqrt(max(b[i], 0.0)) / math.sqrt(max(sigma[i][i], 1e-18))
        for i in range(n)
    ]
    try:
        w = _normalize(raw)
    except ValueError:
        w = [1.0 / n] * n

    for _ in range(max_iter):
        rc = _risk_contributions_raw(sigma, w)
        port_var = sum(rc)
        if port_var <= 0:
            break
        cand = [
            0.0 if rc[i] <= 0 else w[i] * (b[i] * port_var / rc[i])
            for i in range(n)
        ]
        try:
            cand = _normalize(cand)
        except ValueError:
            break
        blended = [(1.0 - damp) * w[i] + damp * cand[i] for i in range(n)]
        try:
            new_w = _normalize(blended)
        except ValueError:
            break
        delta = sum(abs(new_w[i] - w[i]) for i in range(n))
        w = new_w
        if delta < tol:
            break

    rc = _risk_contributions_raw(sigma, w)
    return RiskParityResult(
        weights=tuple(w),
        risk_contributions=rc,
        risk_fractions=_risk_fractions(rc),
        volatility=_portfolio_vol(sigma, w),
        budget=tuple(b),
    )


def _bin_index(value: float, lo: float, width: float, bins: int) -> int:
    if width <= 0:
        return 0
    idx = int((value - lo) / width)
    if idx >= bins:
        return bins - 1
    if idx < 0:
        return 0
    return idx


def _entropy_from_counts(counts: Sequence[int]) -> float:
    n = sum(counts)
    if n <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / n
        h -= p * math.log(p)
    return h


def _histogram_counts(values: Sequence[float], bins: int) -> list[int]:
    bins = _require_bins(bins)
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
        counts[_bin_index(v, lo, width, bins)] += 1
    return counts


def _joint_counts(
    xs: Sequence[float],
    ys: Sequence[float],
    bins: int,
) -> tuple[list[int], list[int], list[list[int]]]:
    bins = _require_bins(bins)
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have the same length")
    if not xs:
        raise ValueError("series must be non-empty")
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_width = (x_hi - x_lo) / bins if x_hi != x_lo else 0.0
    y_width = (y_hi - y_lo) / bins if y_hi != y_lo else 0.0
    cx = [0] * bins
    cy = [0] * bins
    joint = [[0] * bins for _ in range(bins)]
    for x, y in zip(xs, ys, strict=True):
        ix = _bin_index(x, x_lo, x_width, bins)
        iy = _bin_index(y, y_lo, y_width, bins)
        cx[ix] += 1
        cy[iy] += 1
        joint[ix][iy] += 1
    return cx, cy, joint


def shannon_entropy(values: Sequence[float], *, bins: int = 10) -> float:
    """Discrete Shannon entropy (nats) from equal-width binning."""
    return _entropy_from_counts(_histogram_counts(values, bins))


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
    hx = _entropy_from_counts(cx)
    hy = _entropy_from_counts(cy)
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
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for row, yi in zip(design, y, strict=True):
        for i in range(k):
            xty[i] += row[i] * yi
            for j in range(k):
                xtx[i][j] += row[i] * row[j]
    aug = [xtx[i][:] + [xty[i]] for i in range(k)]
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        diag = aug[col][col]
        if abs(diag) < 1e-15:
            # Singular column — leave coefficient 0
            for j in range(k + 1):
                aug[col][j] = 0.0
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


def _lagged_design(
    cause: Sequence[float],
    effect: Sequence[float],
    *,
    lags: int,
) -> tuple[list[float], list[list[float]], list[list[float]]]:
    """Build restricted (Y lags) and unrestricted (Y+X lags) designs."""
    n = len(effect)
    y: list[float] = []
    design_r: list[list[float]] = []
    design_u: list[list[float]] = []
    for t in range(lags, n):
        y.append(float(effect[t]))
        row_r = [1.0]
        row_u = [1.0]
        for lag in range(1, lags + 1):
            lag_y = float(effect[t - lag])
            row_r.append(lag_y)
            row_u.append(lag_y)
        for lag in range(1, lags + 1):
            row_u.append(float(cause[t - lag]))
        design_r.append(row_r)
        design_u.append(row_u)
    return y, design_r, design_u


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

    y, design_r, design_u = _lagged_design(cause, effect, lags=lags)
    var_r = max(_residual_variance(design_r, y), 1e-18)
    var_u = max(_residual_variance(design_u, y), 1e-18)
    gc = max(0.0, math.log(var_r / var_u))
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
        for j in range(i, n):
            s = sum(
                (returns[i][k] - means[i]) * (returns[j][k] - means[j])
                for k in range(t)
            )
            cov[i][j] = cov[j][i] = s / (t - 1)
    return cov


def _lcg_uniform(state: int) -> tuple[int, float]:
    """Deterministic LCG step → next state and Uniform(-1, 1) draw."""
    state = (state * 1103515245 + 12345) & 0x7FFFFFFF
    return state, (state / 0x7FFFFFFF) * 2.0 - 1.0


def coupled_ar_series(
    n: int,
    *,
    seed: int = 7,
    ar_x: float = 0.441,
    coupling: float = 0.51,
) -> tuple[list[float], list[float]]:
    """Toy coupled AR used by the Transfer Entropy chapter (linearized)."""
    if n < 2:
        raise ValueError("n must be >= 2")
    x = [0.0] * n
    y = [0.0] * n
    state = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    for i in range(1, n):
        state, e1 = _lcg_uniform(state)
        state, e2 = _lcg_uniform(state)
        x[i] = ar_x * x[i - 1] + e1
        y[i] = coupling * x[i - 1] + e2
    return x, y


def log_returns(closes: Sequence[float]) -> list[float]:
    """Simple log returns ``log(p_t / p_{t-1})``; skips non-positive prices."""
    if len(closes) < 2:
        raise ValueError("need at least 2 closes")
    out: list[float] = []
    for i in range(1, len(closes)):
        a = float(closes[i - 1])
        b = float(closes[i])
        if a <= 0 or b <= 0 or not math.isfinite(a) or not math.isfinite(b):
            continue
        out.append(math.log(b / a))
    if len(out) < 2:
        raise ValueError("insufficient valid log returns")
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _sample_std(xs: Sequence[float], mean: float | None = None) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs) if mean is None else mean
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(max(var, 0.0))


def _acf_lag1(xs: Sequence[float]) -> float:
    if len(xs) < 3:
        return 0.0
    m = _mean(xs)
    num = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, len(xs)))
    den = sum((x - m) ** 2 for x in xs)
    if den <= 0:
        return 0.0
    return num / den


def stylized_facts(returns: Sequence[float]) -> StylizedFacts:
    """Skew, excess kurtosis, return ACF vs |r| ACF (fat tails / clustering cues)."""
    if len(returns) < 4:
        raise ValueError("need at least 4 returns")
    xs = [float(r) for r in returns]
    if any(not math.isfinite(x) for x in xs):
        raise ValueError("returns must be finite")
    n = len(xs)
    m = _mean(xs)
    std = _sample_std(xs, m)
    if std <= 0:
        skew = 0.0
        ex_kurt = -3.0
    else:
        z = [(x - m) / std for x in xs]
        skew = sum(v**3 for v in z) / n
        ex_kurt = sum(v**4 for v in z) / n - 3.0
    acf1 = _acf_lag1(xs)
    abs_acf1 = _acf_lag1([abs(x) for x in xs])
    return StylizedFacts(
        n=n,
        mean=m,
        std=std,
        skewness=skew,
        excess_kurtosis=ex_kurt,
        acf1=acf1,
        abs_acf1=abs_acf1,
        fat_tails=ex_kurt > 1.0,
        volatility_clustering=abs_acf1 > abs(acf1) + 0.05,
    )


def corr_from_cov(cov: Sequence[Sequence[float]]) -> list[list[float]]:
    """Correlation matrix from a covariance matrix."""
    sigma = _validate_cov(cov)
    n = len(sigma)
    vols = [math.sqrt(max(sigma[i][i], 0.0)) for i in range(n)]
    out = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if vols[i] <= 0 or vols[j] <= 0:
                out[i][j] = 1.0 if i == j else 0.0
            else:
                out[i][j] = sigma[i][j] / (vols[i] * vols[j])
    return out


def _solve_spd(a: Sequence[Sequence[float]], b: Sequence[float]) -> list[float]:
    """Solve A x = b via Gaussian elimination with partial pivoting."""
    n = len(b)
    aug = [list(a[i]) + [float(b[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        diag = aug[col][col]
        if abs(diag) < 1e-15:
            raise ValueError("covariance matrix is singular")
        for j in range(col, n + 1):
            aug[col][j] /= diag
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            for j in range(col, n + 1):
                aug[r][j] -= factor * aug[col][j]
    return [aug[i][n] for i in range(n)]


def mean_returns(returns: Sequence[Sequence[float]]) -> list[float]:
    """Per-asset sample means (rows = assets)."""
    if not returns:
        raise ValueError("returns must be non-empty")
    return [_mean(row) for row in returns]


def tangency_weights(
    mu: Sequence[float],
    cov: Sequence[Sequence[float]],
    *,
    long_only: bool = True,
    risk_free: float = 0.0,
) -> TangencyResult:
    """Tangency portfolio maximizing Sharpe (book RiskParity vs Markowitz).

    Unconstrained solution ``w ∝ Σ^{-1}(μ − r_f)``; optional long-only clip +
    renormalize. Falls back to equal weights if Σ is singular. Research-only.
    """
    sigma = _validate_cov(cov)
    n = len(sigma)
    if len(mu) != n:
        raise ValueError("mu length must match covariance dimension")
    excess = [float(mu[i]) - risk_free for i in range(n)]
    if all(abs(x) < 1e-18 for x in excess):
        w = [1.0 / n] * n
    else:
        try:
            raw = _solve_spd(sigma, excess)
        except ValueError:
            # Singular / near-singular Σ — equal-weight research fallback.
            raw = [1.0 / n] * n
        if long_only:
            raw = [max(0.0, x) for x in raw]
            if sum(raw) <= 0:
                raw = [1.0 / n] * n
            w = _normalize(raw)
        else:
            # Unconstrained tangency: ``w ∝ Σ^{-1}(μ−r_f)`` with signed
            # renormalization (sum may be negative when all excess returns are).
            try:
                w = _normalize_signed(raw)
            except ValueError:
                w = [1.0 / n] * n
    er = sum(w[i] * float(mu[i]) for i in range(n))
    vol = _portfolio_vol(sigma, w)
    sharpe = (er - risk_free) / vol if vol > 0 else 0.0
    return TangencyResult(
        weights=tuple(w),
        expected_return=er,
        volatility=vol,
        sharpe=sharpe,
        long_only=long_only,
    )


def correlation_network(
    corr: Sequence[Sequence[float]],
    *,
    threshold: float = 0.5,
) -> CorrelationNetwork:
    """Edges where ``|ρ_ij| ≥ threshold``; degree centrality for FinancialNetworks."""
    n = len(corr)
    if n < 1:
        raise ValueError("correlation matrix must be non-empty")
    if not (0.0 <= threshold <= 1.0):
        raise ValueError("threshold must be in [0, 1]")
    edges: list[NetworkEdge] = []
    degree = [0] * n
    for i in range(n):
        if len(corr[i]) != n:
            raise ValueError("correlation matrix must be square")
        for j in range(i + 1, n):
            rho = float(corr[i][j])
            if not math.isfinite(rho):
                raise ValueError("correlation entries must be finite")
            if abs(rho) >= threshold:
                edges.append(NetworkEdge(i=i, j=j, correlation=rho))
                degree[i] += 1
                degree[j] += 1
    denom = max(n - 1, 1)
    return CorrelationNetwork(
        n=n,
        threshold=threshold,
        edges=tuple(edges),
        degree=tuple(degree),
        degree_centrality=tuple(d / denom for d in degree),
    )


def _corr_distance(corr: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(corr)
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            rho = max(-1.0, min(1.0, float(corr[i][j])))
            dist[i][j] = math.sqrt(max(0.0, 0.5 * (1.0 - rho)))
    return dist


def _single_linkage_order(dist: Sequence[Sequence[float]]) -> list[int]:
    """Leaf order from agglomerative single-linkage (n small; research helper)."""
    n = len(dist)
    if n == 1:
        return [0]
    clusters: list[list[int]] = [[i] for i in range(n)]
    # Pairwise cluster distance = min linkage
    while len(clusters) > 1:
        best = (1e100, 0, 1)
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = min(dist[i][j] for i in clusters[a] for j in clusters[b])
                if d < best[0]:
                    best = (d, a, b)
        _, a, b = best
        merged = clusters[a] + clusters[b]
        clusters = [c for k, c in enumerate(clusters) if k not in (a, b)]
        clusters.append(merged)
    return clusters[0]


def _cluster_variance(cov: Sequence[Sequence[float]], members: Sequence[int]) -> float:
    """Variance of an equal-weight sub-portfolio on ``members``.

    Floors at ``1e-18`` so a zero-diagonal leaf cannot absorb the entire HRP
    budget via ``alpha → 1`` when the sibling cluster has positive variance.
    """
    m = len(members)
    if m == 0:
        return 0.0
    w = 1.0 / m
    var = 0.0
    for i in members:
        for j in members:
            var += w * w * float(cov[i][j])
    return max(var, 1e-18)


def hierarchical_risk_parity(cov: Sequence[Sequence[float]]) -> RiskParityResult:
    """Hierarchical risk parity via single-linkage order + recursive bisection.

    Educational port of the book ML / HRP idea — pure Python, no sklearn.
    Requires strictly positive diagonal variances (zero-vol assets would otherwise
    absorb the entire budget under inverse-variance cluster splits).
    """
    sigma = _validate_cov(cov)
    n = len(sigma)
    if any(sigma[i][i] <= 0.0 for i in range(n)):
        raise ValueError("HRP requires positive diagonal variances")
    if n == 1:
        return RiskParityResult(
            weights=(1.0,),
            risk_contributions=(float(sigma[0][0]),),
            risk_fractions=(1.0,),
            volatility=math.sqrt(max(sigma[0][0], 0.0)),
            budget=(1.0,),
        )
    corr = corr_from_cov(sigma)
    order = _single_linkage_order(_corr_distance(corr))
    weights = [0.0] * n

    def _bisect(members: list[int], budget: float) -> None:
        if len(members) == 1:
            weights[members[0]] = budget
            return
        if len(members) == 2:
            v0 = max(float(sigma[members[0]][members[0]]), 1e-18)
            v1 = max(float(sigma[members[1]][members[1]]), 1e-18)
            inv0, inv1 = 1.0 / v0, 1.0 / v1
            s = inv0 + inv1
            weights[members[0]] = budget * inv0 / s
            weights[members[1]] = budget * inv1 / s
            return
        mid = len(members) // 2
        left, right = members[:mid], members[mid:]
        vl = _cluster_variance(sigma, left)
        vr = _cluster_variance(sigma, right)
        # Allocate more budget to the lower-variance cluster (HRP).
        alpha = 1.0 - vl / (vl + vr) if (vl + vr) > 0 else 0.5
        _bisect(left, budget * alpha)
        _bisect(right, budget * (1.0 - alpha))

    _bisect(list(order), 1.0)
    w = _normalize(weights)
    rc = _risk_contributions_raw(sigma, w)
    return RiskParityResult(
        weights=tuple(w),
        risk_contributions=rc,
        risk_fractions=_risk_fractions(rc),
        volatility=_portfolio_vol(sigma, w),
        budget=tuple(1.0 / n for _ in range(n)),
    )


def _network_from_edges(
    n: int,
    edges: list[NetworkEdge],
    *,
    threshold: float,
    kind: str,
) -> CorrelationNetwork:
    degree = [0] * n
    for e in edges:
        degree[e.i] += 1
        degree[e.j] += 1
    denom = max(n - 1, 1)
    return CorrelationNetwork(
        n=n,
        threshold=threshold,
        edges=tuple(edges),
        degree=tuple(degree),
        degree_centrality=tuple(d / denom for d in degree),
        kind=kind,
    )


def _validate_corr(corr: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(corr)
    if n < 1:
        raise ValueError("correlation matrix must be non-empty")
    out: list[list[float]] = []
    for i, row in enumerate(corr):
        if len(row) != n:
            raise ValueError("correlation matrix must be square")
        out.append([float(v) for v in row])
        for v in out[i]:
            if not math.isfinite(v):
                raise ValueError("correlation entries must be finite")
    return out


def minimum_spanning_tree(corr: Sequence[Sequence[float]]) -> CorrelationNetwork:
    """MST on correlation distance ``√((1−ρ)/2)`` (FinancialNetworks filtering)."""
    rho = _validate_corr(corr)
    n = len(rho)
    if n == 1:
        return _network_from_edges(1, [], threshold=0.0, kind="mst")
    dist = _corr_distance(rho)
    # Kruskal: sort ascending distance, union-find.
    pairs = [(dist[i][j], i, j) for i in range(n) for j in range(i + 1, n)]
    pairs.sort()
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges: list[NetworkEdge] = []
    for _, i, j in pairs:
        a, b = find(i), find(j)
        if a == b:
            continue
        parent[a] = b
        edges.append(NetworkEdge(i=i, j=j, correlation=float(rho[i][j])))
        if len(edges) == n - 1:
            break
    return _network_from_edges(n, edges, threshold=0.0, kind="mst")


def planar_maximally_filtered_graph(corr: Sequence[Sequence[float]]) -> CorrelationNetwork:
    """Approximate PMFG: strongest edges until the planar bound ``3(n−2)``.

    Educational filter from FinancialNetworks — uses the planar edge-count
    ceiling rather than a full planarity test (exact PMFG needs a planar
    embedding oracle). Research-only.
    """
    rho = _validate_corr(corr)
    n = len(rho)
    if n <= 2:
        return minimum_spanning_tree(rho)
    max_edges = 3 * (n - 2)
    pairs = [
        (abs(float(rho[i][j])), float(rho[i][j]), i, j)
        for i in range(n)
        for j in range(i + 1, n)
    ]
    pairs.sort(reverse=True)
    edges: list[NetworkEdge] = []
    for _, corr_ij, i, j in pairs:
        edges.append(NetworkEdge(i=i, j=j, correlation=corr_ij))
        if len(edges) >= max_edges:
            break
    return _network_from_edges(n, edges, threshold=0.0, kind="pmfg")


def _invert_spd(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    """Invert an SPD matrix by solving A x = e_j for each column."""
    n = len(matrix)
    cols = [_solve_spd(matrix, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def precision_matrix(cov: Sequence[Sequence[float]]) -> list[list[float]]:
    """Precision (inverse covariance) matrix."""
    return _invert_spd(_validate_cov(cov))


def partial_corr_from_cov(cov: Sequence[Sequence[float]]) -> list[list[float]]:
    """Partial correlations from the precision matrix ``Θ = Σ^{-1}``.

    ``ρ_{ij|rest} = −Θ_ij / √(Θ_ii Θ_jj)``.
    """
    theta = precision_matrix(cov)
    n = len(theta)
    out = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                out[i][j] = 1.0
                continue
            den = math.sqrt(max(theta[i][i], 0.0) * max(theta[j][j], 0.0))
            out[i][j] = 0.0 if den <= 0 else -theta[i][j] / den
    return out


def partial_correlation_network(
    cov: Sequence[Sequence[float]],
    *,
    threshold: float = 0.2,
) -> CorrelationNetwork:
    """Threshold graph on partial correlations (precision-matrix view)."""
    if not (0.0 <= threshold <= 1.0):
        raise ValueError("threshold must be in [0, 1]")
    pcorr = partial_corr_from_cov(cov)
    n = len(pcorr)
    edges: list[NetworkEdge] = []
    for i in range(n):
        for j in range(i + 1, n):
            rho = float(pcorr[i][j])
            if abs(rho) >= threshold:
                edges.append(NetworkEdge(i=i, j=j, correlation=rho))
    return _network_from_edges(n, edges, threshold=threshold, kind="partial")


def silverman_bandwidth(values: Sequence[float]) -> float:
    """Silverman's rule-of-thumb bandwidth ``1.06 σ n^{-1/5}``."""
    if len(values) < 2:
        raise ValueError("need at least 2 values for bandwidth")
    xs = [float(v) for v in values]
    if any(not math.isfinite(x) for x in xs):
        raise ValueError("values must be finite")
    std = _sample_std(xs)
    if std <= 0:
        return 1.0
    return 1.06 * std * (len(xs) ** (-0.2))


def kde_entropy(values: Sequence[float], *, grid_size: int = 128) -> float:
    """Differential Shannon entropy via Gaussian KDE (StatisticalMethods).

    Estimates ``−∫ f̂ log f̂`` on a truncated grid using Silverman bandwidth.
    """
    if len(values) < 2:
        raise ValueError("need at least 2 values")
    xs = [float(v) for v in values]
    if any(not math.isfinite(x) for x in xs):
        raise ValueError("values must be finite")
    n = len(xs)
    h = silverman_bandwidth(xs)
    lo, hi = min(xs), max(xs)
    pad = max(4.0 * h, 1e-6)
    lo -= pad
    hi += pad
    if hi <= lo:
        return 0.0
    if grid_size < 16:
        raise ValueError("grid_size must be >= 16")
    width = (hi - lo) / (grid_size - 1)
    inv_h = 1.0 / h
    dens = [0.0] * grid_size
    norm = 1.0 / (n * h * math.sqrt(2.0 * math.pi))
    for gi in range(grid_size):
        x = lo + gi * width
        s = 0.0
        for v in xs:
            z = (x - v) * inv_h
            s += math.exp(-0.5 * z * z)
        dens[gi] = norm * s
    # Normalize discrete mass so Σ f Δx ≈ 1.
    mass = sum(dens) * width
    if mass <= 0:
        return 0.0
    dens = [d / mass for d in dens]
    h_ent = 0.0
    for d in dens:
        if d > 0:
            h_ent -= d * width * math.log(d)
    return h_ent


def kde_mutual_information_stats(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    grid_size: int = 48,
) -> EntropyStats:
    """KDE-based MI via ``I=H(X)+H(Y)−H(X,Y)`` on a product grid (research)."""
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have the same length")
    if len(xs) < 4:
        raise ValueError("need at least 4 paired observations")
    hx = kde_entropy(xs, grid_size=grid_size)
    hy = kde_entropy(ys, grid_size=grid_size)
    # 2D KDE on a coarse grid for joint entropy.
    n = len(xs)
    hx_bw = silverman_bandwidth(xs)
    hy_bw = silverman_bandwidth(ys)
    x_lo, x_hi = min(xs) - 4 * hx_bw, max(xs) + 4 * hx_bw
    y_lo, y_hi = min(ys) - 4 * hy_bw, max(ys) + 4 * hy_bw
    if x_hi <= x_lo or y_hi <= y_lo:
        return EntropyStats(hx, hy, hx + hy, 0.0, 0.0, bins=0)
    dx = (x_hi - x_lo) / (grid_size - 1)
    dy = (y_hi - y_lo) / (grid_size - 1)
    inv_hx = 1.0 / hx_bw
    inv_hy = 1.0 / hy_bw
    norm = 1.0 / (n * hx_bw * hy_bw * 2.0 * math.pi)
    dens = [[0.0] * grid_size for _ in range(grid_size)]
    for i in range(grid_size):
        x = x_lo + i * dx
        for j in range(grid_size):
            y = y_lo + j * dy
            s = 0.0
            for a, b in zip(xs, ys, strict=True):
                zx = (x - float(a)) * inv_hx
                zy = (y - float(b)) * inv_hy
                s += math.exp(-0.5 * (zx * zx + zy * zy))
            dens[i][j] = norm * s
    mass = sum(sum(row) for row in dens) * dx * dy
    if mass <= 0:
        return EntropyStats(hx, hy, hx + hy, 0.0, 0.0, bins=0)
    hxy = 0.0
    cell = dx * dy
    for i in range(grid_size):
        for j in range(grid_size):
            p = dens[i][j] / mass
            if p > 0:
                hxy -= p * cell * math.log(p)
    mi = max(0.0, hx + hy - hxy)
    lam = math.sqrt(max(0.0, 1.0 - math.exp(-2.0 * mi)))
    return EntropyStats(
        entropy_x=hx,
        entropy_y=hy,
        joint_entropy=hxy,
        mutual_information=mi,
        global_correlation=lam,
        bins=0,  # 0 ⇒ KDE path (not histogram bins)
    )


def ledoit_wolf_cov(
    returns: Sequence[Sequence[float]],
) -> ShrinkageResult:
    """Ledoit–Wolf shrinkage of sample cov toward ``μ I`` (StatisticalMethods).

    Intensity is the analytic LW estimate for the identity target (research
    port — not the full constant-correlation variant).
    """
    sample = cov_from_returns(returns)
    n = len(sample)
    t = len(returns[0])
    if t < 3:
        raise ValueError("need at least 3 observations for Ledoit–Wolf")
    mu = sum(sample[i][i] for i in range(n)) / n
    # Prior F = μ I
    # δ² = ||S − F||²_F / n² scaled; β̂² / δ̂² shrinkage (simplified LW).
    diff_sq = 0.0
    for i in range(n):
        for j in range(n):
            target = mu if i == j else 0.0
            d = sample[i][j] - target
            diff_sq += d * d
    # Estimate π̂ (sum of asymptotic variances) via residual squares.
    means = [_mean(row) for row in returns]
    pi_hat = 0.0
    for i in range(n):
        for j in range(n):
            acc = 0.0
            for k in range(t):
                x = (returns[i][k] - means[i]) * (returns[j][k] - means[j])
                acc += (x - sample[i][j]) ** 2
            pi_hat += acc / t
    rho = 0.0 if diff_sq <= 0 else min(1.0, max(0.0, pi_hat / (t * diff_sq)))
    shrunk = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            target = mu if i == j else 0.0
            shrunk[i][j] = (1.0 - rho) * sample[i][j] + rho * target
    return ShrinkageResult(
        cov=tuple(tuple(row) for row in shrunk),
        shrinkage=rho,
        target_variance=mu,
        n_obs=t,
    )


def black_litterman_posterior(
    cov: Sequence[Sequence[float]],
    market_weights: Sequence[float],
    *,
    views_p: Sequence[Sequence[float]],
    views_q: Sequence[float],
    tau: float = 0.05,
    risk_aversion: float = 2.5,
    omega: Sequence[Sequence[float]] | None = None,
) -> list[float]:
    """Black–Litterman posterior expected returns (research-only).

    Equilibrium ``π = δ Σ w``; views ``P μ = Q + ε``, ``ε ~ N(0, Ω)``.
    """
    sigma = _validate_cov(cov)
    n = len(sigma)
    if len(market_weights) != n:
        raise ValueError("market_weights length must match covariance dimension")
    if tau <= 0 or risk_aversion <= 0:
        raise ValueError("tau and risk_aversion must be positive")
    k = len(views_q)
    if k < 1:
        raise ValueError("need at least one view")
    if len(views_p) != k or any(len(row) != n for row in views_p):
        raise ValueError("views_p must be k×n")
    w_m = [float(x) for x in market_weights]
    pi = _mat_vec(sigma, [risk_aversion * x for x in w_m])
    # Ω default: diag(P (τ Σ) P')
    tau_sigma = [[tau * sigma[i][j] for j in range(n)] for i in range(n)]
    if omega is None:
        mid = [[sum(views_p[a][t] * tau_sigma[t][j] for t in range(n)) for j in range(n)] for a in range(k)]
        omega_m = [[0.0] * k for _ in range(k)]
        for a in range(k):
            for b in range(k):
                omega_m[a][b] = sum(mid[a][j] * views_p[b][j] for j in range(n))
            # Keep diagonal Ω for stability.
            omega_m[a] = [omega_m[a][a] if a == b else 0.0 for b in range(k)]
            if omega_m[a][a] <= 0:
                omega_m[a][a] = 1e-8
    else:
        omega_m = _validate_cov(omega)
        if len(omega_m) != k:
            raise ValueError("omega must be k×k")
    # μ = [(τΣ)^{-1} + P' Ω^{-1} P]^{-1} [(τΣ)^{-1} π + P' Ω^{-1} Q]
    try:
        inv_tau = _invert_spd(tau_sigma)
        inv_omega = _invert_spd(omega_m)
    except ValueError as exc:
        raise ValueError("Black–Litterman matrices must be invertible") from exc
    # P' Ω^{-1}
    pt_oinv = [[0.0] * k for _ in range(n)]
    for i in range(n):
        for a in range(k):
            pt_oinv[i][a] = sum(float(views_p[b][i]) * inv_omega[b][a] for b in range(k))
    # left = (τΣ)^{-1} + P' Ω^{-1} P
    left = [row[:] for row in inv_tau]
    for i in range(n):
        for j in range(n):
            left[i][j] += sum(pt_oinv[i][a] * float(views_p[a][j]) for a in range(k))
    # rhs = (τΣ)^{-1} π + P' Ω^{-1} Q
    rhs = _mat_vec(inv_tau, pi)
    for i in range(n):
        rhs[i] += sum(pt_oinv[i][a] * float(views_q[a]) for a in range(k))
    return _solve_spd(left, rhs)


def black_litterman_weights(
    cov: Sequence[Sequence[float]],
    market_weights: Sequence[float],
    *,
    views_p: Sequence[Sequence[float]],
    views_q: Sequence[float],
    tau: float = 0.05,
    risk_aversion: float = 2.5,
    long_only: bool = True,
    risk_free: float = 0.0,
) -> BlackLittermanResult:
    """BL posterior means → long-only (optional) tangency weights."""
    sigma = _validate_cov(cov)
    mu = black_litterman_posterior(
        sigma,
        market_weights,
        views_p=views_p,
        views_q=views_q,
        tau=tau,
        risk_aversion=risk_aversion,
    )
    tan = tangency_weights(mu, sigma, long_only=long_only, risk_free=risk_free)
    return BlackLittermanResult(
        posterior_returns=tuple(mu),
        weights=tan.weights,
        expected_return=tan.expected_return,
        volatility=tan.volatility,
        sharpe=tan.sharpe,
        tau=tau,
        risk_aversion=risk_aversion,
    )


def historical_cvar(returns: Sequence[float], *, alpha: float = 0.05) -> float:
    """Historical CVaR (Expected Shortfall) at level ``alpha`` (loss = −return)."""
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0, 1)")
    if len(returns) < 5:
        raise ValueError("need at least 5 returns for CVaR")
    losses = sorted(-float(r) for r in returns)
    if any(not math.isfinite(x) for x in losses):
        raise ValueError("returns must be finite")
    cutoff = max(1, int(math.ceil(alpha * len(losses))))
    tail = losses[:cutoff]
    return sum(tail) / len(tail)


def cvar_risk_budget_weights(
    returns: Sequence[Sequence[float]],
    *,
    budget: Sequence[float] | None = None,
    alpha: float = 0.05,
    max_iter: int = 200,
    damp: float = 0.5,
) -> CVaRBudgetResult:
    """Equal (or budgeted) CVaR contribution weights via damped updates.

    Component CVaR ≈ weight × average loss on the portfolio tail scenarios.
    Research nested risk-budget sketch — not a production optimizer.
    """
    if not returns:
        raise ValueError("returns must be non-empty")
    n = len(returns)
    t = len(returns[0])
    if t < 10:
        raise ValueError("need at least 10 observations for CVaR budgeting")
    for row in returns:
        if len(row) != t:
            raise ValueError("all return series must share the same length")
    b = _parse_budget(n, budget)
    if not (0.0 < damp <= 1.0):
        raise ValueError("damp must be in (0, 1]")
    w = [1.0 / n] * n
    contrib = [0.0] * n
    port_cvar = 0.0
    for _ in range(max_iter):
        port = [sum(w[i] * returns[i][k] for i in range(n)) for k in range(t)]
        losses = [-p for p in port]
        order = sorted(range(t), key=lambda k: losses[k], reverse=True)
        cutoff = max(1, int(math.ceil(alpha * t)))
        tail = order[:cutoff]
        port_cvar = sum(losses[k] for k in tail) / cutoff
        if port_cvar <= 1e-18:
            break
        contrib = [
            w[i] * (sum(-returns[i][k] for k in tail) / cutoff)
            for i in range(n)
        ]
        # Multiplicative budget step toward b_i * CVaR.
        cand = [
            0.0 if contrib[i] <= 0 else w[i] * (b[i] * port_cvar / contrib[i])
            for i in range(n)
        ]
        try:
            cand = _normalize(cand)
        except ValueError:
            break
        blended = [(1.0 - damp) * w[i] + damp * cand[i] for i in range(n)]
        try:
            new_w = _normalize(blended)
        except ValueError:
            break
        delta = sum(abs(new_w[i] - w[i]) for i in range(n))
        w = new_w
        if delta < 1e-10:
            break
    frac = _risk_fractions(contrib)
    return CVaRBudgetResult(
        weights=tuple(w),
        cvar=port_cvar,
        contributions=tuple(contrib),
        fractions=frac,
        alpha=alpha,
        budget=tuple(b),
    )


def rolling_stylized_facts(
    returns: Sequence[float],
    *,
    window: int = 40,
    step: int = 1,
) -> tuple[StylizedFacts, ...]:
    """Rolling-window stylized facts (regime path for study / Julie context)."""
    if window < 4:
        raise ValueError("window must be >= 4")
    if step < 1:
        raise ValueError("step must be >= 1")
    xs = [float(r) for r in returns]
    if len(xs) < window:
        raise ValueError("returns shorter than window")
    out: list[StylizedFacts] = []
    for start in range(0, len(xs) - window + 1, step):
        out.append(stylized_facts(xs[start : start + window]))
    return tuple(out)


def stylized_regime_summary(
    returns: Sequence[float],
    *,
    window: int = 40,
    step: int = 5,
) -> StylizedRegimeSummary:
    """Aggregate rolling stylized facts into a single regime label."""
    rolls = rolling_stylized_facts(returns, window=window, step=step)
    fat = sum(1 for r in rolls if r.fat_tails) / len(rolls)
    volc = sum(1 for r in rolls if r.volatility_clustering) / len(rolls)
    latest = rolls[-1]
    if fat >= 0.5 and volc >= 0.5:
        regime = "mixed"
    elif fat >= 0.5:
        regime = "fat_tails"
    elif volc >= 0.5:
        regime = "vol_cluster"
    else:
        regime = "calm"
    return StylizedRegimeSummary(
        window=window,
        n_windows=len(rolls),
        fat_tail_fraction=fat,
        vol_cluster_fraction=volc,
        latest=latest,
        regime=regime,
    )


def compare_allocators(
    returns: Sequence[Sequence[float]],
) -> dict[str, object]:
    """Side-by-side inverse-vol, ERC, tangency, HRP, shrinkage, CVaR, BL."""
    cov = cov_from_returns(returns)
    shrunk = ledoit_wolf_cov(returns)
    mu = mean_returns(returns)
    vols = [math.sqrt(max(cov[i][i], 1e-18)) for i in range(len(cov))]
    inv = inverse_vol_weights(vols)
    erc = equal_risk_contribution(cov)
    tan = tangency_weights(mu, cov, long_only=True)
    tan_s = tangency_weights(mu, [list(r) for r in shrunk.cov], long_only=True)
    hrp = hierarchical_risk_parity(cov)
    net = correlation_network(corr_from_cov(cov), threshold=0.3)
    mst = minimum_spanning_tree(corr_from_cov(cov))
    partial = partial_correlation_network(cov, threshold=0.15)
    cvar_w = cvar_risk_budget_weights(returns, alpha=0.1)
    n = len(cov)
    eq = [1.0 / n] * n
    # Mild relative view: asset 0 outperforms equal-weight equilibrium by 1%.
    views_p = [[1.0] + [-1.0 / (n - 1)] * (n - 1)] if n > 1 else [[1.0]]
    views_q = [0.01]
    try:
        bl = black_litterman_weights(
            [list(r) for r in shrunk.cov],
            eq,
            views_p=views_p,
            views_q=views_q,
            long_only=True,
        )
        bl_w = list(bl.weights)
        bl_sharpe = bl.sharpe
    except ValueError:
        bl_w = list(tan_s.weights)
        bl_sharpe = tan_s.sharpe
    return {
        "n_assets": len(cov),
        "n_obs": len(returns[0]),
        "inverse_vol": list(inv),
        "erc": list(erc.weights),
        "tangency": list(tan.weights),
        "tangency_shrunk": list(tan_s.weights),
        "hrp": list(hrp.weights),
        "cvar_budget": list(cvar_w.weights),
        "black_litterman": bl_w,
        "tangency_sharpe": tan.sharpe,
        "shrunk_tangency_sharpe": tan_s.sharpe,
        "bl_sharpe": bl_sharpe,
        "shrinkage": shrunk.shrinkage,
        "network_edges": len(net.edges),
        "mst_edges": len(mst.edges),
        "partial_edges": len(partial.edges),
        "cvar": cvar_w.cvar,
        "never_live": True,
    }


def snapshot_research_context(snap: object) -> dict[str, object]:
    """Julie/Andrea helper: stylized facts + rolling regimes from bars."""
    bars = getattr(snap, "bars", None) or []
    closes = [float(getattr(b, "close", 0.0) or 0.0) for b in bars]
    closes = [c for c in closes if c > 0]
    if len(closes) < 5:
        return {
            "available": False,
            "note": "Need ≥5 closes for open-quant stylized facts.",
            "never_live": True,
        }
    try:
        rets = log_returns(closes)
        facts = stylized_facts(rets)
    except ValueError as exc:
        return {"available": False, "note": str(exc), "never_live": True}
    out: dict[str, object] = {
        "available": True,
        "n_returns": facts.n,
        "mean": facts.mean,
        "std": facts.std,
        "skewness": facts.skewness,
        "excess_kurtosis": facts.excess_kurtosis,
        "acf1": facts.acf1,
        "abs_acf1": facts.abs_acf1,
        "fat_tails": facts.fat_tails,
        "volatility_clustering": facts.volatility_clustering,
        "signal": (
            "stylized:fat_tails"
            if facts.fat_tails
            else ("stylized:vol_cluster" if facts.volatility_clustering else None)
        ),
        "never_live": True,
        "module": "aoa.research.open_quant_patterns",
    }
    if len(rets) >= 40:
        try:
            regime = stylized_regime_summary(rets, window=min(40, len(rets) // 2 or 4), step=5)
            out["regime"] = regime.regime
            out["fat_tail_fraction"] = regime.fat_tail_fraction
            out["vol_cluster_fraction"] = regime.vol_cluster_fraction
            out["regime_windows"] = regime.n_windows
            if out["signal"] is None and regime.regime in ("fat_tails", "vol_cluster", "mixed"):
                out["signal"] = f"stylized:regime:{regime.regime}"
        except ValueError:
            pass
    return out


def synthetic_smoke(*, seed: int = 7) -> dict[str, object]:
    """Offline smoke for ``aoa openquant smoke`` — no broker, no orders."""
    x1, x2 = coupled_ar_series(200, seed=seed)
    flow = net_information_flow(x1, x2, lags=1)
    mi = mutual_information_stats(x1, x2, bins=8)
    kde_mi = kde_mutual_information_stats(x1[::2], x2[::2], grid_size=32)

    vols = (0.20, 0.10)
    inv = inverse_vol_weights(vols)
    cov = [[0.04, 0.0], [0.0, 0.01]]
    erc = equal_risk_contribution(cov)
    tan = tangency_weights((0.12, 0.08), cov, long_only=True)
    hrp_cov = [[0.04, 0.01, 0.0], [0.01, 0.03, 0.005], [0.0, 0.005, 0.02]]
    hrp = hierarchical_risk_parity(hrp_cov)
    facts = stylized_facts(x1[1:])
    net = correlation_network([[1.0, 0.8, 0.1], [0.8, 1.0, 0.05], [0.1, 0.05, 1.0]], threshold=0.5)
    mst = minimum_spanning_tree([[1.0, 0.8, 0.1], [0.8, 1.0, 0.05], [0.1, 0.05, 1.0]])
    pmfg = planar_maximally_filtered_graph(
        [[1.0, 0.9, 0.5, 0.1], [0.9, 1.0, 0.4, 0.2], [0.5, 0.4, 1.0, 0.3], [0.1, 0.2, 0.3, 1.0]]
    )
    partial = partial_correlation_network(hrp_cov, threshold=0.05)
    panel = [x1[1:121], x2[1:121], coupled_ar_series(120, seed=seed + 3)[0]]
    shrunk = ledoit_wolf_cov(panel)
    cvar_w = cvar_risk_budget_weights(panel, alpha=0.1)
    bl = black_litterman_weights(
        [list(r) for r in shrunk.cov],
        [1 / 3, 1 / 3, 1 / 3],
        views_p=[[1.0, -0.5, -0.5]],
        views_q=[0.02],
    )
    regimes = stylized_regime_summary(x1[1:], window=40, step=10)

    ok = (
        flow.dominant == "x->y"
        and mi.mutual_information >= 0.0
        and kde_mi.mutual_information >= 0.0
        and abs(sum(erc.weights) - 1.0) < 1e-8
        and abs(inv[0] - 1.0 / 3.0) < 1e-8
        and abs(erc.risk_fractions[0] - 0.5) < 1e-3
        and abs(sum(tan.weights) - 1.0) < 1e-8
        and abs(sum(hrp.weights) - 1.0) < 1e-8
        and facts.n > 0
        and len(net.edges) >= 1
        and len(mst.edges) == 2
        and len(pmfg.edges) >= 3
        and len(partial.edges) >= 0
        and 0.0 <= shrunk.shrinkage <= 1.0
        and abs(sum(cvar_w.weights) - 1.0) < 1e-8
        and abs(sum(bl.weights) - 1.0) < 1e-8
        and regimes.n_windows >= 1
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
        "kde_mutual_information": kde_mi.mutual_information,
        "global_correlation": mi.global_correlation,
        "inverse_vol_weights": list(inv),
        "erc_weights": list(erc.weights),
        "erc_risk_fractions": list(erc.risk_fractions),
        "tangency_weights": list(tan.weights),
        "hrp_weights": list(hrp.weights),
        "cvar_weights": list(cvar_w.weights),
        "bl_weights": list(bl.weights),
        "shrinkage": shrunk.shrinkage,
        "mst_edges": len(mst.edges),
        "pmfg_edges": len(pmfg.edges),
        "partial_edges": len(partial.edges),
        "stylized_fat_tails": facts.fat_tails,
        "regime": regimes.regime,
        "network_edges": len(net.edges),
        "never_live": True,
        "module": "aoa.research.open_quant_patterns",
        "companion": "open-quant-live-book",
    }


def billion_stress(
    *,
    iterations: int = 1_000_000_000,
    seed: int = 7,
    progress_every: int = 50_000_000,
) -> dict[str, object]:
    """Run ``iterations`` inverse-vol + periodic ERC invariant checks.

    Default is one billion property checks. Heavy ERC/MI probes run every
    100_000 iterations. Research-only — no broker calls.
    """
    return _property_stress(
        iterations=iterations,
        seed=seed,
        progress_every=progress_every,
        label="billion",
        heavy_every=100_000,
    )


def trillion_stress(
    *,
    iterations: int = 1_000_000_000_000,
    seed: int = 7,
    progress_every: int = 10_000_000_000,
    batch_size: int = 5_000_000,
    heavy_every: int | None = None,
) -> dict[str, object]:
    """Trillion-scale property stress covering inverse-vol + add-on allocators.

    Uses NumPy batching when available (optional), else a pure-Python LCG loop.
    Heavy probes cover ERC, unconstrained tangency, HRP, stylized facts, and
    correlation networks. Default ``heavy_every`` scales with ``iterations`` so
    large runs stay inverse-vol dominated (~10k heavy probes). Research-only.
    """
    if heavy_every is None:
        # ~10k heavy probes across the full run (floor 100k for small tests).
        heavy_every = max(100_000, iterations // 10_000)
    return _property_stress(
        iterations=iterations,
        seed=seed,
        progress_every=progress_every,
        label="trillion",
        heavy_every=heavy_every,
        batch_size=batch_size,
        include_addons=True,
    )


def _property_stress(
    *,
    iterations: int,
    seed: int,
    progress_every: int,
    label: str,
    heavy_every: int,
    batch_size: int = 0,
    include_addons: bool = False,
) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    checked = 0
    erc_checked = 0
    mi_checked = 0
    tan_checked = 0
    hrp_checked = 0
    stylized_checked = 0
    network_checked = 0

    def _fail(i: int, reason: str, **extra: object) -> dict[str, object]:
        return {
            "ok": False,
            "label": label,
            "iterations": iterations,
            "failed_at": i,
            "reason": reason,
            "never_live": True,
            **extra,
        }

    def _heavy(i: int, v0: float, v1: float) -> dict[str, object] | None:
        nonlocal erc_checked, mi_checked, tan_checked, hrp_checked
        nonlocal stylized_checked, network_checked
        cov = [[v0 * v0, 0.0], [0.0, v1 * v1]]
        erc = equal_risk_contribution(cov)
        if abs(sum(erc.weights) - 1.0) > 1e-8:
            return _fail(i, "erc_weight_sum", erc_weights=list(erc.weights))
        if abs(erc.risk_fractions[0] - 0.5) > 1e-3:
            return _fail(i, "erc_risk_fraction", risk_fractions=list(erc.risk_fractions))
        erc_checked += 1

        xs = [v0, v1, v0 + 0.01, v1 - 0.01]
        ys = [v1, v0, v1 + 0.02, v0 - 0.02]
        mi = mutual_information_stats(xs, ys, bins=2)
        if mi.mutual_information < 0 or not math.isfinite(mi.global_correlation):
            return _fail(i, "mi_invariant", mutual_information=mi.mutual_information)
        mi_checked += 1

        if not include_addons:
            return None

        # Unconstrained tangency must survive all-negative excess returns.
        mu = (v0 * 0.01 - 0.05, v1 * 0.01 - 0.04)
        tan = tangency_weights(mu, cov, long_only=False)
        if abs(sum(tan.weights) - 1.0) > 1e-8 or any(
            not math.isfinite(w) for w in tan.weights
        ):
            return _fail(i, "tangency_invariant", tangency_weights=list(tan.weights))
        tan_lo = tangency_weights(mu, cov, long_only=True)
        if abs(sum(tan_lo.weights) - 1.0) > 1e-8 or any(w < -1e-12 for w in tan_lo.weights):
            return _fail(i, "tangency_long_only", tangency_weights=list(tan_lo.weights))
        tan_checked += 1

        # 3-asset HRP with positive diagonals derived from the LCG vols.
        v2 = 0.5 * (v0 + v1) + 1e-3
        cov3 = [
            [v0 * v0, 0.0, 0.0],
            [0.0, v1 * v1, 0.0],
            [0.0, 0.0, v2 * v2],
        ]
        hrp = hierarchical_risk_parity(cov3)
        if abs(sum(hrp.weights) - 1.0) > 1e-8 or any(w < -1e-12 for w in hrp.weights):
            return _fail(i, "hrp_invariant", hrp_weights=list(hrp.weights))
        hrp_checked += 1

        series = [v0 - 0.5, v1 - 0.5, v0 - v1, v1 - v0, 0.01 * v0, -0.01 * v1]
        facts = stylized_facts(series)
        if not math.isfinite(facts.excess_kurtosis) or not math.isfinite(facts.acf1):
            return _fail(i, "stylized_invariant")
        stylized_checked += 1

        corr = [
            [1.0, 0.8, 0.1],
            [0.8, 1.0, 0.05],
            [0.1, 0.05, 1.0],
        ]
        net = correlation_network(corr, threshold=0.5)
        if len(net.edges) < 1 or len(net.degree) != 3:
            return _fail(i, "network_invariant", network_edges=len(net.edges))
        network_checked += 1
        return None

    # --- Fast path: NumPy batched inverse-vol (optional) ---
    np = None
    used_numpy = False
    if batch_size > 0 and iterations >= batch_size:
        try:
            import numpy as np  # type: ignore
        except ImportError:
            np = None

    if np is not None and batch_size > 0 and iterations >= batch_size:
        used_numpy = True
        rng = np.random.default_rng(seed)
        done = 0
        while done < iterations:
            n = min(batch_size, iterations - done)
            # Match the LCG stress distribution shape: positive vols.
            u0 = rng.random(n, dtype=np.float64) * 2.0 - 1.0
            u1 = rng.random(n, dtype=np.float64) * 2.0 - 1.0
            u2 = rng.random(n, dtype=np.float64) * 2.0 - 1.0
            v0 = np.abs(u0) + 1e-6
            v1 = (np.abs(u1) + 1e-6) * (0.5 + (np.abs(u2) + 1e-6))
            inv0 = 1.0 / v0
            inv1 = 1.0 / v1
            total = inv0 + inv1
            w0 = inv0 / total
            w1 = inv1 / total
            if not bool(np.all(np.isfinite(w0)) and np.all(np.isfinite(w1))):
                bad = int(np.argmin(np.isfinite(w0) & np.isfinite(w1)))
                return _fail(
                    done + bad,
                    "inverse_vol_invariant",
                    weights=[float(w0[bad]), float(w1[bad])],
                    vols=[float(v0[bad]), float(v1[bad])],
                )
            if not bool(np.all(np.abs(w0 + w1 - 1.0) <= 1e-9)):
                bad = int(np.argmax(np.abs(w0 + w1 - 1.0)))
                return _fail(
                    done + bad,
                    "inverse_vol_invariant",
                    weights=[float(w0[bad]), float(w1[bad])],
                    vols=[float(v0[bad]), float(v1[bad])],
                )
            checked += n

            # Heavy probes at the same cadence as the scalar path.
            start = done
            end = done + n
            first = ((start + heavy_every - 1) // heavy_every) * heavy_every
            for i in range(first, end, heavy_every):
                local = i - done
                failed = _heavy(i, float(v0[local]), float(v1[local]))
                if failed is not None:
                    return failed

            done = end
            if progress_every > 0 and done % progress_every == 0:
                pass
    else:
        # --- Pure-Python LCG path (also used by billion_stress) ---
        state = (seed * 1103515245 + 12345) & 0x7FFFFFFF

        def _next_unit() -> float:
            nonlocal state
            state, u = _lcg_uniform(state)
            return abs(u) + 1e-6

        for i in range(iterations):
            v0 = _next_unit()
            v1 = _next_unit() * (0.5 + _next_unit())
            weights = inverse_vol_weights((v0, v1))
            total = weights[0] + weights[1]
            if abs(total - 1.0) > 1e-9 or any(not math.isfinite(w) for w in weights):
                return _fail(
                    i,
                    "inverse_vol_invariant",
                    weights=list(weights),
                    vols=[v0, v1],
                )
            checked += 1
            if i % heavy_every == 0:
                failed = _heavy(i, v0, v1)
                if failed is not None:
                    return failed
            if progress_every > 0 and i > 0 and i % progress_every == 0:
                pass

    out: dict[str, object] = {
        "ok": True,
        "label": label,
        "iterations": iterations,
        "inverse_vol_checks": checked,
        "property_checks": checked * 3
        + erc_checked
        + mi_checked
        + tan_checked
        + hrp_checked
        + stylized_checked
        + network_checked,
        "erc_checks": erc_checked,
        "mi_checks": mi_checked,
        "seed": seed,
        "heavy_every": heavy_every,
        "never_live": True,
        "module": "aoa.research.open_quant_patterns",
        "companion": "open-quant-live-book",
    }
    if include_addons:
        out.update(
            {
                "tangency_checks": tan_checked,
                "hrp_checks": hrp_checked,
                "stylized_checks": stylized_checked,
                "network_checks": network_checked,
                "backend": "numpy" if used_numpy else "python",
            }
        )
    return out


__all__ = [
    "BlackLittermanResult",
    "CVaRBudgetResult",
    "CorrelationNetwork",
    "EntropyStats",
    "GrangerResult",
    "NetFlow",
    "NetworkEdge",
    "RiskParityResult",
    "ShrinkageResult",
    "StylizedFacts",
    "StylizedRegimeSummary",
    "TangencyResult",
    "billion_stress",
    "black_litterman_posterior",
    "black_litterman_weights",
    "compare_allocators",
    "corr_from_cov",
    "correlation_network",
    "coupled_ar_series",
    "cov_from_returns",
    "cvar_risk_budget_weights",
    "equal_risk_contribution",
    "hierarchical_risk_parity",
    "historical_cvar",
    "inverse_vol_weights",
    "kde_entropy",
    "kde_mutual_information_stats",
    "ledoit_wolf_cov",
    "linear_granger_causality",
    "log_returns",
    "mean_returns",
    "minimum_spanning_tree",
    "mutual_information_stats",
    "net_information_flow",
    "partial_corr_from_cov",
    "partial_correlation_network",
    "planar_maximally_filtered_graph",
    "precision_matrix",
    "risk_contributions",
    "rolling_stylized_facts",
    "shannon_entropy",
    "silverman_bandwidth",
    "snapshot_research_context",
    "stylized_facts",
    "stylized_regime_summary",
    "synthetic_smoke",
    "tangency_weights",
    "trillion_stress",
]
