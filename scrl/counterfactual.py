"""Factor-model counterfactuals. Probabilities are not claimed; these are stress cases."""

from __future__ import annotations

from dataclasses import dataclass

from scrl.factors import FactorSnapshot


@dataclass
class Scenario:
    name: str
    brent_shock: float
    benchmark_shock: float
    fx_shock: float
    implied_equity: float
    note: str


def project(factor: FactorSnapshot, brent: float, benchmark: float, fx: float) -> float:
    # Use 20-session stacked daily betas as a rough 20d translator.
    # residual assumed unchanged (honest: we do not invent alpha).
    return (
        factor.beta_benchmark * benchmark
        + factor.beta_brent * brent
        + factor.beta_fx * fx
        + factor.residual_20 * 0.0
    )


def scenarios(factor: FactorSnapshot) -> list[Scenario]:
    specs = [
        ("W1_brent_fades_risk_on", -0.08, 0.03, -0.01, "Brent −8%, Nifty +3%, INR slightly stronger"),
        ("W2_sanctions_risk_off", 0.08, -0.04, 0.02, "Brent +8%, Nifty −4%, INR weaker"),
        ("W3_chop", 0.00, 0.00, 0.00, "No factor shock; path noise only"),
    ]
    out = []
    for name, b, m, fx, note in specs:
        px = project(factor, b, m, fx)
        out.append(
            Scenario(
                name=name,
                brent_shock=b,
                benchmark_shock=m,
                fx_shock=fx,
                implied_equity=px,
                note=note,
            )
        )
    return out
