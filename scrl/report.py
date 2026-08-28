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
    h = r.analogs.horizon_days
    paper = "none" if r.permission.decision in {"DENY", "WAIT"} else "journal this decision; defined-risk / scheduled lot only"

    return f"""SCRL TICKET  {r.ticker} | mandate={r.mandate.name} ({r.mandate.label}) | as-of {r.as_of.date()}
close {r.close:.2f}

TODAY: {r.permission.today}

PERMISSION: {r.permission.decision}
CASH WEIGHT (new risk): {r.permission.cash_weight:.2f}
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

4. SITUATION RETRIEVAL  k={analog.n} past episodes (point-in-time; {h}d already realized)
   fwd_{h}  p25={_pct(analog.fwd_10['p25'])}  median={_pct(analog.fwd_10['median'])}  p75={_pct(analog.fwd_10['p75'])}
   excess_{h} vs nifty  p25={_pct(analog.fwd_excess_10['p25'])}  median={_pct(analog.fwd_excess_10['median'])}  p75={_pct(analog.fwd_excess_10['p75'])}
   straddles_zero={analog.straddles_zero}  same_sign={analog.same_sign}
   this is a prior, not a forecast. opposite-sign quartiles block swing/position entries, not a long-term HOLD.

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
   - no mixing of swing, position, and long-term into one buy
   - no promotion to live capital; journal first

PAPER ACTION: {paper}
"""


def render_desk(swing: AnalysisResult, position: AnalysisResult, longterm: AnalysisResult) -> str:
    """One page: what you do today across mandates. This is the personal-use surface."""
    rows = [("SWING", swing), ("POSITION", position), ("LONG-TERM", longterm)]
    lines = [
        f"SCRL DESK  {swing.ticker}  as-of {swing.as_of.date()}  close {swing.close:.2f}",
        "",
        "This is how the research loop becomes a trading/investing habit.",
        "You do not get one signal. You get three separate jobs. Mixing them is how you lose.",
        "",
    ]
    for name, r in rows:
        lines.append(f"[{name}]  {r.permission.decision}")
        lines.append(f"  TODAY: {r.permission.today}")
        if r.permission.reasons:
            lines.append("  why: " + " | ".join(r.permission.reasons[:3]))
        lines.append("")
    lines += [
        "INTRADAY: not available on this data. Needs 1-minute bars, costs, and a session clock.",
        "",
        "HOW THIS HELPS P&L",
        "  Swing DENY  = you skip coin-flip 1–4 week trades (usually the expensive hobby).",
        "  Position    = same idea at 20–60 days; still no entry if analogs straddle zero.",
        "  Long-term   = you may HOLD a compounder without needing a 10-day edge;",
        "                you only ADD when 60-day analogs agree, else WAIT to start.",
        "  Journal     = every override is scored later. That file is what you monetize,",
        "                not a Telegram tip feed.",
        "",
        "MONETIZE ONLY AFTER the journal beats buy-and-hold and beats 'always trade'",
        "on the same names, costs included, for many months. Sell the process/software,",
        "not stock tips (that is a regulated activity in India).",
    ]
    return "\n".join(lines) + "\n"


def render_markdown(result: AnalysisResult) -> str:
    return "```\n" + render_text(result) + "```\n"
