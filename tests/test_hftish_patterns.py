"""Tests for example-hftish pattern helpers (order-book imbalance reference)."""

from __future__ import annotations

import math

import pytest

from aoa.research.hftish_patterns import (
    Side,
    TopOfBook,
    arms_after_level_change,
    book_imbalance_side,
    book_width,
    detect_level_change,
    follow_print_signal,
    imbalance_ratio,
    is_penny_spread,
    position_allows_buy,
    position_allows_sell,
    prices_match,
    trade_follows_quote,
)


def test_penny_spread_and_level_change():
    assert is_penny_spread(10.00, 10.01)
    assert not is_penny_spread(10.00, 10.02)
    assert book_width(10.00, 10.01) == pytest.approx(0.01)

    prev = TopOfBook(10.00, 10.01, bid_size=200, ask_size=100, timestamp_ms=1_000.0)
    # Both sides move to a new penny spread → level change
    current = TopOfBook(10.01, 10.02, bid_size=500, ask_size=100, timestamp_ms=1_100.0)
    change = detect_level_change(prev, current)
    assert change is not None
    assert change.spread == pytest.approx(0.01)
    assert change.prev_spread == pytest.approx(0.01)
    assert arms_after_level_change(change)

    # Only bid moves → no level change
    assert detect_level_change(prev, TopOfBook(10.01, 10.01, 1, 1)) is None
    # Wide spread after move → ignored
    wide = TopOfBook(10.00, 10.05, 1, 1, timestamp_ms=1_200.0)
    assert detect_level_change(prev, wide) is None
    # Float noise that is not a real move → ignored
    noisy = TopOfBook(10.00 + 1e-12, 10.01 + 1e-12, 1, 1)
    assert detect_level_change(prev, noisy) is None


def test_diagnose_rejects_bad_quotes():
    from aoa.research.hftish_patterns import diagnose_quote_book

    assert diagnose_quote_book(10.02, 10.01, 100, 50).available is False
    neg = diagnose_quote_book(10.00, 10.01, -5, 100)
    assert neg.available is True  # negative size clamped to 0 → ask-only book
    assert neg.side is Side.SELL
    assert neg.bid_size == 0.0
    both_neg = diagnose_quote_book(10.00, 10.01, -1, -1)
    assert both_neg.available is False


def test_imbalance_and_position_gates():
    assert book_imbalance_side(200, 100, threshold=1.8) is Side.BUY
    assert book_imbalance_side(100, 200, threshold=1.8) is Side.SELL
    assert book_imbalance_side(100, 100, threshold=1.8) is Side.FLAT
    assert imbalance_ratio(180, 100) == pytest.approx(1.8)
    assert math.isinf(imbalance_ratio(10, 0))

    assert position_allows_buy(0, 0, max_shares=500, lot=100)
    assert not position_allows_buy(300, 100, max_shares=500, lot=100)
    assert position_allows_sell(100, 0, lot=100)
    assert not position_allows_sell(100, 50, lot=100)

    with pytest.raises(ValueError):
        book_imbalance_side(1, 1, threshold=0)
    with pytest.raises(ValueError):
        position_allows_buy(0, 0, max_shares=50, lot=100)


def test_follow_print_buy_and_sell():
    quote = TopOfBook(10.01, 10.02, bid_size=500, ask_size=100, timestamp_ms=1_000.0)
    assert trade_follows_quote(1_000.0, 1_060.0, min_lag_ms=50.0)
    assert not trade_follows_quote(1_000.0, 1_040.0, min_lag_ms=50.0)
    assert prices_match(10.02, 10.0200001)

    buy = follow_print_signal(
        quote,
        trade_price=10.02,
        trade_size=100,
        trade_timestamp_ms=1_100.0,
        armed=True,
        total_shares=0,
        max_shares=500,
    )
    assert buy.side is Side.BUY
    assert buy.reason == "follow_ask_imbalance"

    sell_quote = TopOfBook(10.01, 10.02, bid_size=100, ask_size=500, timestamp_ms=1_000.0)
    sell = follow_print_signal(
        sell_quote,
        trade_price=10.01,
        trade_size=150,
        trade_timestamp_ms=1_100.0,
        armed=True,
        total_shares=200,
    )
    assert sell.side is Side.SELL
    assert sell.reason == "follow_bid_imbalance"


def test_follow_print_guards():
    quote = TopOfBook(10.01, 10.02, bid_size=500, ask_size=100, timestamp_ms=1_000.0)
    assert follow_print_signal(
        quote,
        trade_price=10.02,
        trade_size=100,
        trade_timestamp_ms=1_100.0,
        armed=False,
    ).reason == "not_armed"
    assert follow_print_signal(
        quote,
        trade_price=10.02,
        trade_size=100,
        trade_timestamp_ms=1_010.0,
        armed=True,
    ).reason == "trade_too_soon"
    assert follow_print_signal(
        quote,
        trade_price=10.02,
        trade_size=50,
        trade_timestamp_ms=1_100.0,
        armed=True,
    ).reason == "trade_too_small"
    assert follow_print_signal(
        quote,
        trade_price=10.02,
        trade_size=100,
        trade_timestamp_ms=1_100.0,
        armed=True,
        total_shares=400,
        max_shares=500,
    ).reason == "buy_capacity"
