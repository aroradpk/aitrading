from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InstrumentKind(StrEnum):
    INDEX = "index"
    EQUITY = "equity"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    kind: InstrumentKind
    yahoo_ticker: str


NIFTY = Instrument("NIFTY", "Nifty 50", InstrumentKind.INDEX, "^NSEI")
BANKNIFTY = Instrument("BANKNIFTY", "Bank Nifty", InstrumentKind.INDEX, "^NSEBANK")
BAJFINANCE = Instrument("BAJFINANCE", "Bajaj Finance", InstrumentKind.EQUITY, "BAJFINANCE.NS")

UNIVERSE: tuple[Instrument, ...] = (NIFTY, BANKNIFTY, BAJFINANCE)
BY_SYMBOL = {item.symbol: item for item in UNIVERSE}
BENCHMARK_SYMBOL = NIFTY.symbol
SECTOR_BENCHMARK_SYMBOL = BANKNIFTY.symbol
