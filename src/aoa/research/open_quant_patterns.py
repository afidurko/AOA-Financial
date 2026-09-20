"""Pure-Python helpers from afidurko/open-quant-live-book (souzatharsis).

Educational / research reference only. Ports ideas from the Risk Parity,
Entropy, and Transfer Entropy chapters — no R/bookdown runtime, no broker
calls, and no live order path. AOA remains the only execution surface.
"""

from __future__ import annotations

import math
import sys
import time
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


def _normalize(values: Sequence[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        raise ValueError("cannot normalize non-positive weights")
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
    for i in range(n):
        for j in range(i + 1, n):
            if abs(out[i][j] - out[j][i]) > 1e-9:
                raise ValueError("covariance matrix must be symmetric")
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


def synthetic_smoke(*, seed: int = 7) -> dict[str, object]:
    """Offline smoke for ``aoa openquant smoke`` — no broker, no orders."""
    x1, x2 = coupled_ar_series(200, seed=seed)
    flow = net_information_flow(x1, x2, lags=1)
    mi = mutual_information_stats(x1, x2, bins=8)

    vols = (0.20, 0.10)
    inv = inverse_vol_weights(vols)
    erc = equal_risk_contribution([[0.04, 0.0], [0.0, 0.01]])

    ok = (
        flow.dominant == "x->y"
        and mi.mutual_information >= 0.0
        and abs(sum(erc.weights) - 1.0) < 1e-8
        and abs(inv[0] - 1.0 / 3.0) < 1e-8
        and abs(erc.risk_fractions[0] - 0.5) < 1e-3
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
        "erc_risk_fractions": list(erc.risk_fractions),
        "never_live": True,
        "module": "aoa.research.open_quant_patterns",
        "companion": "open-quant-live-book",
    }


_LCG_A = 1103515245
_LCG_C = 12345
_LCG_M = 0x7FFFFFFF
_HEAVY_EVERY = 100_000


def _unit_from_state(state: int) -> tuple[int, float]:
    """LCG step → Uniform-derived positive unit in ``(1e-6, 1+1e-6]``."""
    state = (state * _LCG_A + _LCG_C) & _LCG_M
    return state, abs((state / _LCG_M) * 2.0 - 1.0) + 1e-6


def _fail(
    *,
    iterations: int,
    failed_at: int,
    reason: str,
    **extra: object,
) -> dict[str, object]:
    out: dict[str, object] = {
        "ok": False,
        "iterations": iterations,
        "failed_at": failed_at,
        "reason": reason,
        "never_live": True,
    }
    out.update(extra)
    return out


def _heavy_probes(v0: float, v1: float, state: int) -> tuple[int, dict[str, object] | None]:
    """Periodic ERC / MI / 3-asset probes. Returns (new_state, failure_or_None)."""
    cov = [[v0 * v0, 0.0], [0.0, v1 * v1]]
    erc = equal_risk_contribution(cov)
    if abs(sum(erc.weights) - 1.0) > 1e-8:
        return state, {"reason": "erc_weight_sum", "erc_weights": list(erc.weights)}
    if abs(erc.risk_fractions[0] - 0.5) > 1e-3:
        return state, {
            "reason": "erc_risk_fraction",
            "risk_fractions": list(erc.risk_fractions),
        }

    xs = [v0, v1, v0 + 0.01, v1 - 0.01]
    ys = [v1, v0, v1 + 0.02, v0 - 0.02]
    mi = mutual_information_stats(xs, ys, bins=2)
    if mi.mutual_information < 0 or not math.isfinite(mi.global_correlation):
        return state, {
            "reason": "mi_invariant",
            "mutual_information": mi.mutual_information,
        }

    rho = 0.25
    cov_c = [[v0 * v0, rho * v0 * v1], [rho * v0 * v1, v1 * v1]]
    erc_c = equal_risk_contribution(cov_c)
    if abs(sum(erc_c.weights) - 1.0) > 1e-8:
        return state, {"reason": "erc_corr_weight_sum", "erc_weights": list(erc_c.weights)}
    if abs(sum(erc_c.risk_fractions) - 1.0) > 1e-8:
        return state, {
            "reason": "erc_corr_frac_sum",
            "risk_fractions": list(erc_c.risk_fractions),
        }

    state, v2 = _unit_from_state(state)
    w3 = inverse_vol_weights((v0, v1, v2))
    if abs(sum(w3) - 1.0) > 1e-9 or any(not math.isfinite(w) for w in w3):
        return state, {
            "reason": "inverse_vol_3_invariant",
            "weights": list(w3),
            "vols": [v0, v1, v2],
        }
    return state, None


def _billion_stress_shard(
    iterations: int,
    seed: int,
    progress_every: int,
    shard_id: int,
    index_offset: int,
) -> dict[str, object]:
    """One sequential shard of :func:`billion_stress` (picklable for workers)."""
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    started = time.perf_counter()
    state = (seed * _LCG_A + _LCG_C) & _LCG_M
    checked = 0
    erc_checked = 0
    mi_checked = 0
    corr_checked = 0
    triple_checked = 0
    heavy_in = 0
    progress_in = progress_every if progress_every > 0 else 0

    for i in range(iterations):
        state, v0 = _unit_from_state(state)
        state, u1 = _unit_from_state(state)
        state, u2 = _unit_from_state(state)
        v1 = u1 * (0.5 + u2)
        inv0 = 1.0 / v0
        inv1 = 1.0 / v1
        total_inv = inv0 + inv1
        w0 = inv0 / total_inv
        w1 = inv1 / total_inv
        if (
            not math.isfinite(w0)
            or not math.isfinite(w1)
            or abs(w0 + w1 - 1.0) > 1e-9
        ):
            return _fail(
                iterations=iterations,
                failed_at=index_offset + i,
                reason="inverse_vol_invariant",
                weights=[w0, w1],
                vols=[v0, v1],
                shard=shard_id,
            )
        checked += 1

        if heavy_in == 0:
            state, probe_fail = _heavy_probes(v0, v1, state)
            if probe_fail is not None:
                return _fail(
                    iterations=iterations,
                    failed_at=index_offset + i,
                    shard=shard_id,
                    **probe_fail,
                )
            erc_checked += 1
            mi_checked += 1
            corr_checked += 1
            triple_checked += 1
            heavy_in = _HEAVY_EVERY
        heavy_in -= 1

        if progress_in > 0:
            progress_in -= 1
            if progress_in == 0:
                elapsed = time.perf_counter() - started
                print(
                    f"openquant-stress shard{shard_id} {i + 1}/{iterations} ({elapsed:.1f}s)",
                    file=sys.stderr,
                    flush=True,
                )
                progress_in = progress_every

    return {
        "ok": True,
        "iterations": iterations,
        "inverse_vol_checks": checked,
        "erc_checks": erc_checked,
        "mi_checks": mi_checked,
        "erc_corr_checks": corr_checked,
        "inverse_vol_3_checks": triple_checked,
        "elapsed_s": time.perf_counter() - started,
        "seed": seed,
        "shard": shard_id,
        "never_live": True,
        "module": "aoa.research.open_quant_patterns",
        "companion": "open-quant-live-book",
    }


def billion_stress(
    *,
    iterations: int = 1_000_000_000,
    seed: int = 7,
    progress_every: int = 50_000_000,
    workers: int = 1,
) -> dict[str, object]:
    """Run ``iterations`` inverse-vol + periodic ERC invariant checks.

    Default is one billion property checks. Heavy ERC/MI probes run every
    100_000 iterations. ``workers>1`` shards the work across processes
    (distinct seeds; total checks still sum to ``iterations``).
    Research-only — no broker calls.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    n_workers = max(1, int(workers))
    if n_workers == 1 or iterations < n_workers:
        return _billion_stress_shard(iterations, seed, progress_every, 0, 0)

    from concurrent.futures import ProcessPoolExecutor, as_completed

    started = time.perf_counter()
    base, rem = divmod(iterations, n_workers)
    shards: list[tuple[int, int, int, int]] = []
    offset = 0
    for i in range(n_workers):
        n = base + (1 if i < rem else 0)
        if n <= 0:
            continue
        shards.append((n, seed + i * 9973, i, offset))
        offset += n

    merged = {
        "ok": True,
        "iterations": iterations,
        "inverse_vol_checks": 0,
        "erc_checks": 0,
        "mi_checks": 0,
        "erc_corr_checks": 0,
        "inverse_vol_3_checks": 0,
        "workers": n_workers,
        "seed": seed,
        "never_live": True,
        "module": "aoa.research.open_quant_patterns",
        "companion": "open-quant-live-book",
    }
    with ProcessPoolExecutor(max_workers=len(shards)) as pool:
        futs = [
            pool.submit(_billion_stress_shard, n, shard_seed, progress_every, shard_id, off)
            for n, shard_seed, shard_id, off in shards
        ]
        for fut in as_completed(futs):
            part = fut.result()
            if not part.get("ok"):
                part["elapsed_s"] = time.perf_counter() - started
                part["workers"] = n_workers
                return part
            merged["inverse_vol_checks"] = int(merged["inverse_vol_checks"]) + int(
                part["inverse_vol_checks"]
            )
            for key in ("erc_checks", "mi_checks", "erc_corr_checks", "inverse_vol_3_checks"):
                merged[key] = int(merged[key]) + int(part[key])
    merged["elapsed_s"] = time.perf_counter() - started
    return merged


# Named stress scales for CLI / loop tasks.
# ``trillion`` is a 3×billion property sample (full 1e12 is opt-in via --iterations).
STRESS_SCALES: dict[str, int] = {
    "smoke": 250_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "trillion": 3_000_000_000,
}


def scale_stress(
    scale: str,
    *,
    seed: int = 7,
    iterations: int | None = None,
    workers: int = 1,
) -> dict[str, object]:
    """Run :func:`billion_stress` for a named scale (or explicit iterations)."""
    key = (scale or "smoke").strip().lower()
    if iterations is None:
        if key not in STRESS_SCALES:
            raise ValueError(
                f"Unknown scale {scale!r}; choose one of {sorted(STRESS_SCALES)}"
            )
        iterations = STRESS_SCALES[key]
    result = billion_stress(iterations=iterations, seed=seed, workers=workers)
    result["scale"] = key if key in STRESS_SCALES else "custom"
    return result


__all__ = [
    "EntropyStats",
    "GrangerResult",
    "NetFlow",
    "RiskParityResult",
    "STRESS_SCALES",
    "billion_stress",
    "coupled_ar_series",
    "cov_from_returns",
    "equal_risk_contribution",
    "inverse_vol_weights",
    "linear_granger_causality",
    "mutual_information_stats",
    "net_information_flow",
    "risk_contributions",
    "scale_stress",
    "shannon_entropy",
    "synthetic_smoke",
]
