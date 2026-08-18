"""Budget gate: check an estimate against a team's monthly envelope."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import yaml

from . import config

Verdict = Literal["ok", "warn", "over"]


@lru_cache(maxsize=1)
def _teams() -> dict:
    with open(config.COST_CENTERS_FILE) as f:
        return yaml.safe_load(f)["teams"]


@dataclass
class BudgetResult:
    verdict: Verdict
    team: str
    cost_center: str
    owner: str
    monthly_budget_usd: float
    current_spend_usd: float
    projected_usd: float
    headroom_usd: float
    message: str


def check(team: str, monthly_estimate_usd: float) -> BudgetResult:
    teams = _teams()
    if team not in teams:
        raise ValueError(
            f"Unknown team '{team}'. Known teams: {', '.join(sorted(teams))}"
        )
    t = teams[team]
    budget = float(t["monthly_budget_usd"])
    spend = float(t["current_spend_usd"])
    projected = round(spend + monthly_estimate_usd, 2)
    headroom = round(budget - projected, 2)

    if projected > budget:
        verdict: Verdict = "over"
        msg = (
            f"OVER budget: this request would put {team} at ${projected:.2f} "
            f"against a ${budget:.2f} envelope (${-headroom:.2f} over). "
            f"Requires an approval label to proceed."
        )
    elif projected > budget * 0.9:
        verdict = "warn"
        msg = (
            f"Within budget but tight: {team} would sit at ${projected:.2f} "
            f"of ${budget:.2f} (${headroom:.2f} headroom)."
        )
    else:
        verdict = "ok"
        msg = (
            f"Within budget: {team} would sit at ${projected:.2f} of "
            f"${budget:.2f} (${headroom:.2f} headroom)."
        )

    return BudgetResult(
        verdict=verdict,
        team=team,
        cost_center=t["cost_center"],
        owner=t["owner"],
        monthly_budget_usd=budget,
        current_spend_usd=spend,
        projected_usd=projected,
        headroom_usd=headroom,
        message=msg,
    )
