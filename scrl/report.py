"""Compile a research ticket. No target prices. No marketing language."""

from __future__ import annotations

from scrl.pipeline import AnalysisResult


def _pct(x: float | None, digits: int = 2) -> str:
    if x is None or x != x:
        return "n/a"
    return f"{x * 100:.{digits}f}%"


def _f(x: float | None, digits: int = 3) -> str:
    if x is None or x != x:
        return "n/a"
    return f"{x:.{digits}f}"


def render_text(result: AnalysisResult) -> str:
    r = result
    probs = "  ".join(f"P({k})={v:.2f}" for k, v in sorted(r.regime.probabilities.items()))
    analog = r.analogs
    kills = "\n".join(f"    - {k}" for k in r.adversary.kills) or "    - none"
    warns = "\n".join(f"    - {w}" for w in r.adversary.warnings) or "    - none"
    reasons = "\n".join(f"    - {x}" for x in r.permission.reasons) or "    - none"
    scen_lines = "\n".join(
        f"    {s.name}: implied ~{_pct(s.implied_equity)}  ({s.note})" for s in r.scenarios
    )
    t = r.board.trend
    f = r.board.fade
    c = r.board.cash
    le = r.last_earnings.isoformat() if r.last_earnings else "not supplied"

    return f"""SCRL TICKET  {r.ticker} | horizon {r.horizon_days} sessions | as-of {r.as_of.date()}
close {r.close:.2f}

PERMISSION: {r.permission.decision}
CASH WEIGHT: {r.permission.cash_weight:.2f}
REASONS:
{reasons}

1. WORLD STATE
   close={r.close:.2f}  dist_52w_high={_pct(float(r.features_row['dist_52w_high']))}  dist_ma20={_pct(float(r.features_row['dist_ma20']))}
   eq_20={_pct(float(r.features_row['eq_ret_20']))}  nifty_20={_pct(float(r.features_row['bm_ret_20']))}  excess_20={_pct(float(r.features_row['excess_20']))}
   brent_20={_pct(float(r.features_row['brent_ret_20']))}  range_20={_pct(float(r.features_row['range_20']))}
   monthly expiry in {r.days_to_expiry} day(s)  last_earnings={le}

2. REGIME (mixture, not a headline)
   state={r.regime.state}  entropy={r.regime.entropy:.2f}  high_entropy={r.regime.high_entropy}
   {probs}

3. FACTOR RESIDUAL  equity ~ nifty + brent + usd/inr  (60d rolling OLS)
   residual_20={_pct(r.factor.residual_20)}  R2={_f(r.factor.r_squared, 2)}
   beta_nifty={_f(r.factor.beta_benchmark, 2)}  beta_brent={_f(r.factor.beta_brent, 3)}  beta_fx={_f(r.factor.beta_fx, 3)}
   interpretation: residual is what oil/index/FX do not explain. Small residual = no unused idiosyncratic gap.

4. SITUATION RETRIEVAL  k={analog.n} past episodes (point-in-time; 10d already realized)
   fwd_10  p25={_pct(analog.fwd_10['p25'])}  median={_pct(analog.fwd_10['median'])}  p75={_pct(analog.fwd_10['p75'])}
   excess_10 vs nifty  p25={_pct(analog.fwd_excess_10['p25'])}  median={_pct(analog.fwd_excess_10['median'])}  p75={_pct(analog.fwd_excess_10['p75'])}
   straddles_zero={analog.straddles_zero}  same_sign={analog.same_sign}
   this is a prior, not a forecast. opposite-sign quartiles => no directional trade.

5. SPECIALISTS (walk-forward health only; in-sample Sharpe is ignored)
   trend_follow  fire={t.fire}  healthy={t.healthy}  oos_hit={_f(t.oos_hit_rate, 2)}  oos_mean={_pct(t.oos_mean)}
              {t.reason}
   fade_oversold fire={f.fire}  healthy={f.healthy}  oos_hit={_f(f.oos_hit_rate, 2)}  oos_mean={_pct(f.oos_mean)}
              {f.reason}
   cash          fire={c.fire}
   disagreement={r.board.disagreement}

6. DEGRADATION
   {r.degradation.note}
   degraded={r.degradation.degraded}

7. COUNTERFACTUALS  (stress through the factor model; NOT probabilities)
{scen_lines}
   residual is held at 0 in the projection. If you cannot live with W2, you do not have a 1–4w long.

8. ADVERSARY
   KILLS:
{kills}
   WARNINGS:
{warns}

9. WHAT THIS SYSTEM WILL NOT SAY
   - no target price
   - no "AI confidence %"
   - no 12-month Jio/new-energy story inside a {r.horizon_days}-session ticket
   - no promotion to live capital; this is a research permission flag

PAPER ACTION: {"none" if r.permission.decision == "DENY" else "defined-risk only, size clipped by cash_weight"}
"""


def render_markdown(result: AnalysisResult) -> str:
    return "```\n" + render_text(result) + "```\n"
