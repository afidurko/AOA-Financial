"""Pine Script v6 ``strategy()`` generator for every TradingView desk preset.

The emitted script and :mod:`aoa.tradingview.rules` implement the same rules:
signals are evaluated on confirmed bars, entries fill on the next bar open
(TradingView default), protective stop/target/trailing exits are ATR-based,
equities are long-only inside a regular-hours session and flat into the close,
and every order carries a JSON ``alert_message`` for webhook routing.

Paste the output into TradingView → Pine Editor → *Add to chart*. Create an
alert on the strategy with *Order fills only* and message
``{{strategy.order.alert_message}}`` to route fills to the AOA webhook
(``POST /api/tradingview/webhook``). Nothing executes without the human.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from aoa.tradingview.presets import Preset

_INDENT = "    "


def _f(x: float) -> str:
    s = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return s if "." in s else f"{s}.0"


def _b(x: bool) -> str:
    return "true" if x else "false"


def _title(preset: Preset) -> str:
    return f"AOA {preset.name}"


def _short(preset: Preset) -> str:
    parts = preset.name.split("-")
    return ("AOA-" + "-".join(p[:4] for p in parts[:3])).upper()[:20]


def _alert_payload(preset: Preset, event: str) -> str:
    """Build the Pine expression for a JSON alert message."""
    head = json.dumps(
        {"source": "aoa-tradingview", "preset": preset.name, "event": event, "market": preset.market}
    )[:-1]  # drop closing brace; we append dynamic fields
    return (
        "'"
        + head.replace("'", "\\'")
        + ',"ticker":"\' + syminfo.ticker + \'","exchange":"\' + syminfo.prefix + '
        + "'\",\"tf\":\"' + timeframe.period + '\",\"price\":' + str.tostring(close) + "
        + "',\"time\":' + str.tostring(time) + '}'"
    )


def _header(preset: Preset) -> list[str]:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    r = preset.risk
    c = preset.costs
    lines = [
        "//@version=6",
        f"// AOA Financial — TradingView desk preset: {preset.name}",
        f"// {preset.description}",
        f"// horizon={preset.horizon} market={preset.market} timeframe={preset.tf.label} generated={stamp}",
        "// The same rules are backtested offline by aoa.tradingview.backtest (TradingView fill semantics).",
        "// Human has final say: this script only emits alerts. Route them to POST /api/tradingview/webhook.",
        f'strategy("{_title(preset)}", shorttitle="{_short(preset)}", overlay=true,',
        f"{_INDENT} initial_capital=100000, currency=currency.USD,",
        f"{_INDENT} default_qty_type=strategy.percent_of_equity, default_qty_value={_f(r.qty_pct_equity)},",
        f"{_INDENT} commission_type=strategy.commission.percent, commission_value={_f(c.commission_pct)},",
        f"{_INDENT} slippage={int(c.slippage_ticks)}, pyramiding=0, calc_on_every_tick=false,",
        f"{_INDENT} process_orders_on_close=false, use_bar_magnifier={_b(preset.use_bar_magnifier)},",
        f"{_INDENT} max_bars_back=500)",
        "",
    ]
    if preset.tf.is_seconds:
        lines.insert(
            6,
            "// NOTE: seconds-based charts require a TradingView Premium+ plan; keep Bar Magnifier on for honest fills.",
        )
    return lines


def _risk_inputs(preset: Preset) -> list[str]:
    r = preset.risk
    lines = [
        'grpRisk = "Risk"',
        f'stopAtr    = input.float({_f(r.stop_atr)}, "Stop (ATR x)", minval=0, step=0.1, group=grpRisk)',
        f'targetAtr  = input.float({_f(r.target_atr)}, "Target (ATR x, 0 = off)", minval=0, step=0.1, group=grpRisk)',
        f'trailAtr   = input.float({_f(r.trail_atr)}, "Trailing stop (ATR x, 0 = off)", minval=0, step=0.1, group=grpRisk)',
        f'maxBars    = input.int({int(r.max_bars_in_trade)}, "Time stop (bars, 0 = off)", minval=0, group=grpRisk)',
        f'maxPerDay  = input.int({int(r.max_trades_per_day)}, "Max entries per day (0 = off)", minval=0, group=grpRisk)',
        f'allowShort = input.bool({_b(preset.allow_short)}, "Allow shorts", group=grpRisk)',
        f'atrLen     = input.int({int(preset.params.get("atr_len", 14))}, "ATR length", minval=1, group=grpRisk)',
    ]
    if r.session:
        lines.append(f'sessInput  = input.session("{r.session}", "Session (exchange time)", group=grpRisk)')
        lines.append('useSession = input.bool(true, "Trade only inside session; flat at session end", group=grpRisk)')
    return lines


def _session_block(preset: Preset) -> list[str]:
    if not preset.risk.session:
        return [
            "inSession      = true",
            "lastSessionBar = false",
        ]
    return [
        "inSession      = not useSession or not na(time(timeframe.period, sessInput, syminfo.timezone))",
        "sessEndHHMM    = str.tonumber(str.substring(sessInput, 5, 9))",
        "closeHHMM      = hour(time_close, syminfo.timezone) * 100 + minute(time_close, syminfo.timezone)",
        "lastSessionBar = useSession and inSession and closeHHMM >= sessEndHHMM",
    ]


def _fundamentals_block(preset: Preset) -> list[str]:
    f = preset.fundamentals
    if not f.enabled or preset.market != "equity":
        return ["fundOk = true"]
    return [
        'grpFund = "Fundamentals (request.financial)"',
        'useFund   = input.bool(true, "Gate entries on fundamentals", group=grpFund)',
        f'maxPE     = input.float({_f(f.max_trailing_pe)}, "Max trailing P/E", minval=0, group=grpFund)',
        f'minEpsG   = input.float({_f(f.min_eps_growth_pct)}, "Min EPS growth % (1y)", group=grpFund)',
        f'minRevG   = input.float({_f(f.min_revenue_growth_pct)}, "Min revenue growth % (1y)", group=grpFund)',
        f'minMargin = input.float({_f(f.min_net_margin_pct)}, "Min net margin %", group=grpFund)',
        f'maxDE     = input.float({_f(f.max_debt_to_equity)}, "Max debt / equity", minval=0, group=grpFund)',
        'epsTTM    = request.financial(syminfo.tickerid, "EARNINGS_PER_SHARE_BASIC", "TTM", ignore_invalid_symbol=true)',
        'epsGrowth = request.financial(syminfo.tickerid, "EARNINGS_PER_SHARE_BASIC_ONE_YEAR_GROWTH", "TTM", ignore_invalid_symbol=true)',
        'revGrowth = request.financial(syminfo.tickerid, "REVENUE_ONE_YEAR_GROWTH", "TTM", ignore_invalid_symbol=true)',
        'netMargin = request.financial(syminfo.tickerid, "NET_MARGIN", "TTM", ignore_invalid_symbol=true)',
        'debtEq    = request.financial(syminfo.tickerid, "DEBT_TO_EQUITY", "FQ", ignore_invalid_symbol=true)',
        "trailingPE = epsTTM > 0 ? close / epsTTM : na",
        "peOk     = na(epsTTM) ? true : epsTTM <= 0 ? false : trailingPE <= maxPE",
        "epsOk    = na(epsGrowth) or epsGrowth >= minEpsG",
        "revOk    = na(revGrowth) or revGrowth >= minRevG",
        "marginOk = na(netMargin) or netMargin >= minMargin",
        "deOk     = na(debtEq) or debtEq <= maxDE",
        "fundOk   = not useFund or (peOk and epsOk and revOk and marginOk and deOk)",
    ]


def _signal_block(preset: Preset) -> list[str]:
    """Emit inputs + indicator math + ``longCond/shortCond/exitLong/exitShort``."""
    p = preset.params
    fam = preset.family
    L: list[str] = ['grpSig = "Signal"']
    if fam == "momentum_scalper":
        L += [
            f'fastLen  = input.int({int(p["ema_fast"])}, "EMA fast", minval=1, group=grpSig)',
            f'slowLen  = input.int({int(p["ema_slow"])}, "EMA slow", minval=2, group=grpSig)',
            f'rsiLen   = input.int({int(p["rsi_len"])}, "RSI length", minval=2, group=grpSig)',
            f'rsiFloor = input.float({_f(p.get("rsi_floor", 52.0))}, "RSI floor (long)", group=grpSig)',
            f'rsiCeil  = input.float({_f(p.get("rsi_ceiling", 85.0))}, "RSI ceiling (long)", group=grpSig)',
            f'volLen   = input.int({int(p.get("vol_len", 20))}, "Volume SMA length", minval=1, group=grpSig)',
            f'volMult  = input.float({_f(p.get("vol_mult", 1.0))}, "Volume surge x", minval=0, step=0.1, group=grpSig)',
            f'useVwap  = input.bool({_b(p.get("use_vwap", True))}, "Require VWAP side", group=grpSig)',
            "",
            "emaFast = ta.ema(close, fastLen)",
            "emaSlow = ta.ema(close, slowLen)",
            "rsiVal  = ta.rsi(close, rsiLen)",
            "volSma  = ta.sma(volume, volLen)",
            "vwapVal = ta.vwap(hlc3)",
            "volOk   = volSma > 0 ? volume >= volMult * volSma : true",
            "aboveVw = not useVwap or close > vwapVal",
            "belowVw = not useVwap or close < vwapVal",
            "crossUp = ta.crossover(emaFast, emaSlow)",
            "crossDn = ta.crossunder(emaFast, emaSlow)",
            "rsiUp   = ta.crossover(rsiVal, rsiFloor)",
            "rsiDn   = ta.crossunder(rsiVal, 100 - rsiFloor)",
            "trendUp = emaFast > emaSlow",
            "longTrig  = crossUp or (trendUp and rsiUp)",
            "shortTrig = crossDn or (not trendUp and rsiDn)",
            "longCond  = longTrig and rsiVal > rsiFloor and rsiVal < rsiCeil and aboveVw and volOk",
            "shortCond = shortTrig and rsiVal < 100 - rsiFloor and rsiVal > 100 - rsiCeil and belowVw and volOk",
            "exitLong  = crossDn",
            "exitShort = crossUp",
            "plot(emaFast, \"EMA fast\", color=color.new(color.teal, 0))",
            "plot(emaSlow, \"EMA slow\", color=color.new(color.orange, 0))",
            "plot(useVwap ? vwapVal : na, \"VWAP\", color=color.new(color.purple, 40))",
        ]
    elif fam == "mean_reversion_bands":
        L += [
            f'bbLen   = input.int({int(p["bb_len"])}, "Bollinger length", minval=2, group=grpSig)',
            f'bbMult  = input.float({_f(p["bb_mult"])}, "Bollinger multiplier", minval=0.1, step=0.1, group=grpSig)',
            f'rsiLen  = input.int({int(p["rsi_len"])}, "RSI length", minval=2, group=grpSig)',
            f'rsiLow  = input.float({_f(p.get("rsi_low", 30.0))}, "RSI oversold", group=grpSig)',
            f'rsiHigh = input.float({_f(p.get("rsi_high", 70.0))}, "RSI overbought", group=grpSig)',
            "",
            "basis  = ta.sma(close, bbLen)",
            "dev    = bbMult * ta.stdev(close, bbLen)",
            "upperB = basis + dev",
            "lowerB = basis - dev",
            "rsiVal = ta.rsi(close, rsiLen)",
            "longCond  = close < lowerB and rsiVal < rsiLow",
            "shortCond = close > upperB and rsiVal > rsiHigh",
            "exitLong  = ta.crossover(close, basis)",
            "exitShort = ta.crossunder(close, basis)",
            "plot(basis, \"Basis\", color=color.new(color.gray, 0))",
            "plot(upperB, \"Upper\", color=color.new(color.red, 30))",
            "plot(lowerB, \"Lower\", color=color.new(color.green, 30))",
        ]
    elif fam == "breakout_donchian":
        L += [
            f'chLen   = input.int({int(p["channel_len"])}, "Donchian length", minval=2, group=grpSig)',
            f'exitLen = input.int({int(p.get("exit_channel_len", max(int(p["channel_len"]) // 2, 1)))}, "Exit channel length", minval=1, group=grpSig)',
            f'volLen  = input.int({int(p.get("vol_len", 20))}, "Volume SMA length", minval=1, group=grpSig)',
            f'volMult = input.float({_f(p.get("vol_mult", 1.0))}, "Volume confirmation x", minval=0, step=0.1, group=grpSig)',
            "",
            "upperCh = ta.highest(high, chLen)[1]",
            "lowerCh = ta.lowest(low, chLen)[1]",
            "exitLo  = ta.lowest(low, exitLen)[1]",
            "exitHi  = ta.highest(high, exitLen)[1]",
            "volSma  = ta.sma(volume, volLen)",
            "volOk   = volSma > 0 ? volume >= volMult * volSma : true",
            "longCond  = close > upperCh and volOk",
            "shortCond = close < lowerCh and volOk",
            "exitLong  = close < exitLo",
            "exitShort = close > exitHi",
            "plot(upperCh, \"Upper channel\", color=color.new(color.teal, 0))",
            "plot(lowerCh, \"Lower channel\", color=color.new(color.orange, 0))",
        ]
    elif fam == "trend_supertrend_macd":
        L += [
            f'stLen    = input.int({int(p["st_len"])}, "Supertrend ATR length", minval=1, group=grpSig)',
            f'stMult   = input.float({_f(p["st_mult"])}, "Supertrend factor", minval=0.1, step=0.1, group=grpSig)',
            f'macdFast = input.int({int(p["macd_fast"])}, "MACD fast", minval=1, group=grpSig)',
            f'macdSlow = input.int({int(p["macd_slow"])}, "MACD slow", minval=2, group=grpSig)',
            f'macdSig  = input.int({int(p["macd_signal"])}, "MACD signal", minval=1, group=grpSig)',
            "",
            "[stLine, stDir] = ta.supertrend(stMult, stLen)",
            "[macdLine, sigLine, histLine] = ta.macd(close, macdFast, macdSlow, macdSig)",
            "flipUp = stDir < 0 and stDir[1] > 0",
            "flipDn = stDir > 0 and stDir[1] < 0",
            "longCond  = stDir < 0 and histLine > 0 and flipUp",
            "shortCond = stDir > 0 and histLine < 0 and flipDn",
            "exitLong  = flipDn",
            "exitShort = flipUp",
            "plot(stLine, \"Supertrend\", color=stDir < 0 ? color.new(color.green, 0) : color.new(color.red, 0), style=plot.style_linebr)",
        ]
    elif fam == "orderflow_imbalance":
        n = int(p["delta_len"])
        L += [
            f'deltaLen = input.int({n}, "Delta window (bars)", minval=2, group=grpSig)',
            f'zLen     = input.int({max(3 * n, 10)}, "Z-score window (bars)", minval=5, group=grpSig)',
            f'zEntry   = input.float({_f(p["z_entry"])}, "Entry z-score", minval=0, step=0.1, group=grpSig)',
            f'zExit    = input.float({_f(p.get("z_exit", 0.0))}, "Exit z-score", step=0.1, group=grpSig)',
            f'volLen   = input.int({int(p.get("vol_len", 20))}, "Volume SMA length", minval=1, group=grpSig)',
            f'volMult  = input.float({_f(p.get("vol_mult", 1.0))}, "Volume filter x", minval=0, step=0.1, group=grpSig)',
            f'useVwap  = input.bool({_b(p.get("use_vwap", True))}, "Require VWAP side", group=grpSig)',
            "",
            "// Bar-level order-flow proxy: close-location-value x volume (no L2 needed).",
            "rng      = high - low",
            "clv      = rng > 0 ? (2 * (close - low) / rng - 1) : 0.0",
            "delta    = clv * volume",
            "cumDelta = math.sum(delta, deltaLen)",
            "cdMean   = ta.sma(cumDelta, zLen)",
            "cdStd    = ta.stdev(cumDelta, zLen)",
            "zScore   = cdStd > 0 ? (cumDelta - cdMean) / cdStd : 0.0",
            "volSma   = ta.sma(volume, volLen)",
            "volOk    = volSma > 0 ? volume >= volMult * volSma : true",
            "vwapVal  = ta.vwap(hlc3)",
            "aboveVw  = not useVwap or close > vwapVal",
            "belowVw  = not useVwap or close < vwapVal",
            "longCond  = zScore > zEntry and aboveVw and volOk",
            "shortCond = zScore < -zEntry and belowVw and volOk",
            "exitLong  = zScore < zExit",
            "exitShort = zScore > -zExit",
            "plot(useVwap ? vwapVal : na, \"VWAP\", color=color.new(color.purple, 40))",
        ]
    elif fam == "fundamental_momentum":
        L += [
            f'smaLen   = input.int({int(p["sma_len"])}, "Trend SMA length", minval=2, group=grpSig)',
            f'momLen   = input.int({int(p["mom_len"])}, "Momentum lookback (bars)", minval=2, group=grpSig)',
            f'momSkip  = input.int({int(p.get("mom_skip", 0))}, "Momentum skip (bars)", minval=0, group=grpSig)',
            f'minMom   = input.float({_f(p.get("min_mom_pct", 0.0))}, "Min momentum %", group=grpSig)',
            "",
            "smaVal  = ta.sma(close, smaLen)",
            "momRef  = close[momLen]",
            "momRec  = close[momSkip]",
            "momPct  = momRef > 0 ? (momRec / momRef - 1) * 100 : 0.0",
            "longCond  = close > smaVal and momPct > minMom",
            "shortCond = false",
            "exitLong  = ta.crossunder(close, smaVal)",
            "exitShort = false",
            "plot(smaVal, \"Trend SMA\", color=color.new(color.blue, 0))",
        ]
    else:  # pragma: no cover - guarded by Preset validation
        raise ValueError(f"unknown family {fam}")
    return L


def _execution_block(preset: Preset) -> list[str]:
    enter_long = _alert_payload(preset, "enter_long")
    enter_short = _alert_payload(preset, "enter_short")
    exit_long = _alert_payload(preset, "exit_long")
    exit_short = _alert_payload(preset, "exit_short")
    return [
        "// ── Execution & risk ────────────────────────────────────────────────────",
        "atrVal = ta.atr(atrLen)",
        "var int   tradesToday = 0",
        "var float entryAtr    = na",
        "var float trailStop   = na",
        'if ta.change(time("D")) != 0',
        f"{_INDENT}tradesToday := 0",
        "justOpened = strategy.position_size != 0 and strategy.position_size[1] == 0",
        "if justOpened",
        f"{_INDENT}tradesToday += 1",
        f"{_INDENT}entryAtr  := atrVal[1]",
        f"{_INDENT}trailStop := na",
        "isLong  = strategy.position_size > 0",
        "isShort = strategy.position_size < 0",
        "flat    = strategy.position_size == 0",
        "barsInTrade = strategy.opentrades > 0 ? bar_index - strategy.opentrades.entry_bar_index(0) : 0",
        "perDayOk = maxPerDay == 0 or tradesToday < maxPerDay",
        "canEnter = flat and inSession and not lastSessionBar and perDayOk and fundOk and barstate.isconfirmed",
        "",
        "// entries fill on the next bar open (process_orders_on_close=false)",
        "if canEnter and longCond",
        f'{_INDENT}strategy.entry("L", strategy.long, alert_message={enter_long})',
        "if canEnter and shortCond and allowShort",
        f'{_INDENT}strategy.entry("S", strategy.short, alert_message={enter_short})',
        "",
        "// protective exits: ATR stop / target / trailing (ratchets on close), time stop, session end",
        "entryPx = strategy.opentrades > 0 ? strategy.opentrades.entry_price(0) : na",
        "if isLong and not na(entryAtr)",
        f"{_INDENT}float fixedStop = stopAtr > 0 ? entryPx - stopAtr * entryAtr : na",
        f"{_INDENT}float tgt       = targetAtr > 0 ? entryPx + targetAtr * entryAtr : na",
        f"{_INDENT}if trailAtr > 0",
        f"{_INDENT}{_INDENT}float cand = close - trailAtr * atrVal",
        f"{_INDENT}{_INDENT}trailStop := na(trailStop) ? cand : math.max(trailStop, cand)",
        f"{_INDENT}float stopPx = na(trailStop) ? fixedStop : na(fixedStop) ? trailStop : math.max(fixedStop, trailStop)",
        f'{_INDENT}strategy.exit("XL", from_entry="L", stop=stopPx, limit=tgt, alert_message={exit_long})',
        "if isShort and not na(entryAtr)",
        f"{_INDENT}float fixedStop = stopAtr > 0 ? entryPx + stopAtr * entryAtr : na",
        f"{_INDENT}float tgt       = targetAtr > 0 ? entryPx - targetAtr * entryAtr : na",
        f"{_INDENT}if trailAtr > 0",
        f"{_INDENT}{_INDENT}float cand = close + trailAtr * atrVal",
        f"{_INDENT}{_INDENT}trailStop := na(trailStop) ? cand : math.min(trailStop, cand)",
        f"{_INDENT}float stopPx = na(trailStop) ? fixedStop : na(fixedStop) ? trailStop : math.min(fixedStop, trailStop)",
        f'{_INDENT}strategy.exit("XS", from_entry="S", stop=stopPx, limit=tgt, alert_message={exit_short})',
        "",
        "timeStop   = maxBars > 0 and barsInTrade >= maxBars",
        "sessionEnd = lastSessionBar or (not inSession and not flat)",
        "if isLong and (exitLong or timeStop or sessionEnd)",
        f'{_INDENT}strategy.close("L", comment=sessionEnd ? "session" : timeStop ? "time" : "signal", alert_message={exit_long}, immediately=sessionEnd)',
        "if isShort and (exitShort or timeStop or sessionEnd)",
        f'{_INDENT}strategy.close("S", comment=sessionEnd ? "session" : timeStop ? "time" : "signal", alert_message={exit_short}, immediately=sessionEnd)',
        "",
        "bgcolor(not inSession ? color.new(color.gray, 92) : na)",
        "plotshape(canEnter and longCond, \"Long signal\", shape.triangleup, location.belowbar, color.new(color.green, 0), size=size.tiny)",
        "plotshape(canEnter and shortCond and allowShort, \"Short signal\", shape.triangledown, location.abovebar, color.new(color.red, 0), size=size.tiny)",
    ]


def generate_pine(preset: Preset) -> str:
    """Return a complete Pine Script v6 strategy for ``preset``."""
    lines: list[str] = []
    lines += _header(preset)
    lines += _signal_block(preset)
    lines.append("")
    lines += _risk_inputs(preset)
    lines.append("")
    lines += _session_block(preset)
    lines.append("")
    lines += _fundamentals_block(preset)
    lines.append("")
    lines += _execution_block(preset)
    lines.append("")
    return "\n".join(lines)


def pine_filename(preset: Preset) -> str:
    return f"{preset.name}.pine"


def lint_pine(source: str) -> list[str]:
    """Cheap structural checks so generated scripts never ship obviously broken.

    Not a Pine compiler: it verifies the version pragma, a single ``strategy()``
    declaration, balanced brackets/quotes per line, and that every referenced
    condition variable is defined.
    """
    problems: list[str] = []
    if not source.startswith("//@version=6"):
        problems.append("missing //@version=6 pragma")
    if source.count("\nstrategy(") != 1:
        problems.append("expected exactly one strategy() declaration")
    for needed in ("longCond", "shortCond", "exitLong", "exitShort", "fundOk", "inSession", "lastSessionBar"):
        if f"{needed} " not in source and f"{needed}=" not in source and f"{needed}  " not in source:
            problems.append(f"{needed} is never defined")
    depth_round = depth_square = 0
    for n, line in enumerate(source.splitlines(), 1):
        code = line.split("//", 1)[0] if not line.lstrip().startswith("//") else ""
        if not code.strip():
            continue
        # strip string literals before counting brackets
        stripped = ""
        quote: str | None = None
        i = 0
        while i < len(code):
            ch = code[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            else:
                stripped += ch
            i += 1
        if quote:
            problems.append(f"line {n}: unterminated string literal")
        depth_round += stripped.count("(") - stripped.count(")")
        depth_square += stripped.count("[") - stripped.count("]")
        if depth_round < 0 or depth_square < 0:
            problems.append(f"line {n}: unbalanced brackets")
            depth_round = max(depth_round, 0)
            depth_square = max(depth_square, 0)
    if depth_round != 0:
        problems.append("unbalanced parentheses at end of script")
    if depth_square != 0:
        problems.append("unbalanced square brackets at end of script")
    return problems
