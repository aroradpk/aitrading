"""End-to-end research loop. Numeric engines first; report is a compiler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from scrl.adversary import AdversaryReport, critique
from scrl.calendar_nse import days_to_monthly_expiry
from scrl.counterfactual import Scenario, scenarios
from scrl.data import MarketBundle, load_bundle
from scrl.degradation import Degradation, check_fade_distance
from scrl.factors import FactorSnapshot, rolling_factor_residual, snapshot as factor_snapshot
from scrl.features import build_features
from scrl.mandates import Mandate, get_mandate
from scrl.permission import Permission, decide
from scrl.regime import RegimeModel, RegimeSnapshot
from scrl.retrieval import AnalogSet, retrieve
from scrl.specialists import SpecialistBoard, evaluate as eval_specialists


@dataclass
class AnalysisResult:
    ticker: str
    as_of: pd.Timestamp
    close: float
    horizon_days: int
    regime: RegimeSnapshot
    analogs: AnalogSet
    factor: FactorSnapshot
    board: SpecialistBoard
    adversary: AdversaryReport
    permission: Permission
    scenarios: list[Scenario]
    degradation: Degradation
    last_earnings: date | None
    days_to_expiry: int
    features_row: pd.Series
    mandate: Mandate


def analyze(
    ticker: str = "RELIANCE.NS",
    as_of: str | pd.Timestamp | None = None,
    horizon_days: int = 20,
    last_earnings: str | date | None = None,
    bundle: MarketBundle | None = None,
    k_analogs: int = 25,
    mandate: str | Mandate = "swing",
) -> AnalysisResult:
    if bundle is None:
        bundle = load_bundle(equity=ticker)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(bundle.equity.index.max())
    earnings = pd.Timestamp(last_earnings).date() if last_earnings is not None else None
    m = mandate if isinstance(mandate, Mandate) else get_mandate(mandate)
    horizon_days = m.horizon_days

    feat = build_features(bundle, as_of=as_of_ts)
    usable = feat.dropna(subset=["bm_ret_20", "bm_vol_20", "brent_ret_20", "trend_strength"])
    if usable.empty:
        raise RuntimeError("Not enough history after feature construction")

    regime_model = RegimeModel()
    regime_model.fit(usable.iloc[:-1] if len(usable) > 200 else usable)
    regime_frame = regime_model.predict_frame(usable)
    regime = regime_model.snapshot(usable, as_of=as_of_ts)

    analogs = retrieve(feat, as_of=as_of_ts, k=k_analogs, horizon_days=m.analog_fwd_days)
    factors = rolling_factor_residual(bundle)
    factor = factor_snapshot(factors, as_of=as_of_ts)
    board = eval_specialists(feat, regime_frame, as_of=as_of_ts)

    as_of_d = pd.Timestamp(regime.date).date()
    dte = days_to_monthly_expiry(as_of_d)
    last_row = feat.loc[:as_of_ts].dropna(subset=["close"]).iloc[-1]
    adversary = critique(
        as_of=as_of_d,
        horizon_days=horizon_days,
        last_earnings=earnings,
        analog_n=analogs.n,
        analog_straddles=analogs.straddles_zero,
        days_to_expiry=dte,
        residual_20=factor.residual_20,
        dist_52w_high=float(last_row["dist_52w_high"]) if pd.notna(last_row["dist_52w_high"]) else None,
        mandate=m,
    )
    permission = decide(
        regime=regime,
        analogs=analogs,
        board=board,
        adversary=adversary,
        as_of=as_of_d,
        horizon_days=horizon_days,
        mandate=m,
    )
    deg = check_fade_distance(feat.loc[:as_of_ts])
    return AnalysisResult(
        ticker=ticker,
        as_of=pd.Timestamp(last_row.name),
        close=float(last_row["close"]),
        horizon_days=horizon_days,
        regime=regime,
        analogs=analogs,
        factor=factor,
        board=board,
        adversary=adversary,
        permission=permission,
        scenarios=scenarios(factor),
        degradation=deg,
        last_earnings=earnings,
        days_to_expiry=dte,
        features_row=last_row,
        mandate=m,
    )


def analyze_desk(
    ticker: str = "RELIANCE.NS",
    as_of: str | pd.Timestamp | None = None,
    last_earnings: str | date | None = None,
    bundle: MarketBundle | None = None,
    k_analogs: int = 25,
) -> dict[str, AnalysisResult]:
    if bundle is None:
        bundle = load_bundle(equity=ticker)
    out: dict[str, AnalysisResult] = {}
    for name in ("swing", "position", "longterm"):
        out[name] = analyze(
            ticker=ticker,
            as_of=as_of,
            last_earnings=last_earnings,
            bundle=bundle,
            k_analogs=k_analogs,
            mandate=name,
        )
    return out

