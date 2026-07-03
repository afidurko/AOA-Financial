"""Tests for persistent state: daily-loss baseline and the settlement ledger."""

from __future__ import annotations

from datetime import date

from aoa.state import StateStore, next_business_day


def test_next_business_day_skips_weekend():
    friday = date(2026, 6, 12)  # Friday
    assert next_business_day(friday) == date(2026, 6, 15)  # Monday
    saturday = date(2026, 6, 13)
    assert next_business_day(saturday) == date(2026, 6, 15)


def test_baseline_persists_within_day(tmp_path):
    store = StateStore(tmp_path / "state.json")
    today = date(2026, 6, 12)
    assert store.starting_equity_for_today(100_000, today) == 100_000
    # A later call the same day keeps the original baseline even if equity moved.
    assert store.starting_equity_for_today(96_000, today) == 100_000


def test_baseline_survives_restart(tmp_path):
    path = tmp_path / "state.json"
    today = date(2026, 6, 12)
    StateStore(path).starting_equity_for_today(100_000, today)
    # A brand-new store (simulating a process restart) reads the persisted baseline.
    reborn = StateStore(path)
    assert reborn.starting_equity_for_today(96_000, today) == 100_000


def test_baseline_resets_on_new_day(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.starting_equity_for_today(100_000, date(2026, 6, 12))
    assert store.starting_equity_for_today(96_000, date(2026, 6, 15)) == 96_000


def test_settlement_ledger_tracks_then_settles(tmp_path):
    store = StateStore(tmp_path / "state.json")
    friday = date(2026, 6, 12)
    store.record_sale(5_000, friday)
    # Same day: proceeds are unsettled.
    assert store.unsettled_cash(friday) == 5_000
    # Monday (the settle date): proceeds have settled and are pruned.
    assert store.unsettled_cash(date(2026, 6, 15)) == 0.0


def test_settlement_ledger_persists(tmp_path):
    path = tmp_path / "state.json"
    friday = date(2026, 6, 12)
    StateStore(path).record_sale(5_000, friday)
    assert StateStore(path).unsettled_cash(friday) == 5_000


def test_unsettled_accumulates(tmp_path):
    store = StateStore(tmp_path / "state.json")
    friday = date(2026, 6, 12)
    store.record_sale(3_000, friday)
    store.record_sale(2_000, friday)
    assert store.unsettled_cash(friday) == 5_000
