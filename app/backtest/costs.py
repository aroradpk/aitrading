from __future__ import annotations

from dataclasses import dataclass

from app.universe import BY_SYMBOL, InstrumentKind


@dataclass(frozen=True)
class CostModel:
    brokerage_rate: float = 0.0003
    brokerage_cap: float = 20.0
    stt_sell_equity: float = 0.00025
    stt_fut_sell: float = 0.0002
    exchange_rate: float = 0.0000297
    sebi_rate: float = 0.000001
    stamp_equity_buy: float = 0.00003
    stamp_fut_buy: float = 0.00002
    ipft_rate: float = 0.000001
    gst_rate: float = 0.18
    slippage_bps: float = 3.0


def _brokerage(notional: float, model: CostModel) -> float:
    return min(notional * model.brokerage_rate, model.brokerage_cap)


def round_trip_cost(notional_entry: float, notional_exit: float, symbol: str, model: CostModel) -> float:
    instrument = BY_SYMBOL[symbol]
    buy_notional = notional_entry
    sell_notional = notional_exit
    brokerage = _brokerage(buy_notional, model) + _brokerage(sell_notional, model)
    exchange = (buy_notional + sell_notional) * model.exchange_rate
    sebi = (buy_notional + sell_notional) * model.sebi_rate
    ipft = (buy_notional + sell_notional) * model.ipft_rate
    gst = model.gst_rate * (brokerage + exchange + sebi)
    if instrument.kind == InstrumentKind.EQUITY:
        stt = sell_notional * model.stt_sell_equity
        stamp = buy_notional * model.stamp_equity_buy
    else:
        stt = sell_notional * model.stt_fut_sell
        stamp = buy_notional * model.stamp_fut_buy
    slippage = (buy_notional + sell_notional) * (model.slippage_bps / 10_000.0)
    return brokerage + exchange + sebi + ipft + gst + stt + stamp + slippage
