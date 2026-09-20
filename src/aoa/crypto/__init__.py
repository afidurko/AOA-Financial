"""Crypto research lane: daily history, day-by-day training, bracketed backtests.

Offline/backtest only — this lane never routes orders to a broker. The four
core assets are Bitcoin, Ethereum, Solana, and XRP; the training calendar
starts at 2007-07-17 and walks every day forward so the learner experiences
each asset's *entire* life (including the pre-inception era, recorded as
no-market days) rather than a reverse-engineered summary.
"""

from aoa.crypto.assets import ASSETS, TRAINING_EPOCH, CryptoAsset, get_asset
from aoa.crypto.backtest import BracketPolicy, CryptoBacktester
from aoa.crypto.history import DailyCandle, HistoryStore
from aoa.crypto.training import DayByDayTrainer, PatternMemory

__all__ = [
    "ASSETS",
    "TRAINING_EPOCH",
    "CryptoAsset",
    "get_asset",
    "DailyCandle",
    "HistoryStore",
    "DayByDayTrainer",
    "PatternMemory",
    "BracketPolicy",
    "CryptoBacktester",
]
