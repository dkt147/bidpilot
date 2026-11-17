"""Connects economics: is a bid worth it, and should you boost?

Formula (widely used in 2026 Connects guides):
    expected profit = contract value x win probability x margin - (Connects cost + time cost)
Boost rule of thumb: boost only on crowded jobs (30+ proposals) where
    contract value / total Connects cost > $200.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

CONNECT_PRICE_USD = 0.15   # bulk store price in 2026; pass your own if it changes


@dataclass
class ConnectsROI:
    contract_value: float
    connects: int
    connect_cost: float
    time_cost: float
    win_probability: float
    expected_revenue: float
    expected_profit: float
    roi_multiple: Optional[float]
    break_even_win_rate: float
    worth_it: bool
    boost_recommended: bool
    boost_max_connects: int
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_contract_value(budget_type: Optional[str], budget_mid: Optional[float],
                            est_hours: float = 40.0) -> Optional[float]:
    if budget_mid is None:
        return None
    return budget_mid * est_hours if budget_type == "hourly" else budget_mid


def connects_roi(contract_value: float, connects: int, win_probability: float,
                 hourly_rate: float = 50.0, hours_per_proposal: float = 0.3,
                 margin: float = 0.7, proposals: Optional[int] = None,
                 connect_price: float = CONNECT_PRICE_USD) -> ConnectsROI:
    connects = max(0, int(connects))
    win_probability = min(max(win_probability, 0.0), 1.0)
    connect_cost = connects * connect_price
    time_cost = hours_per_proposal * hourly_rate
    total_cost = connect_cost + time_cost
    expected_revenue = contract_value * win_probability * margin
    expected_profit = expected_revenue - total_cost
    roi = (expected_revenue / total_cost) if total_cost else None
    denom = contract_value * margin
    break_even = (total_cost / denom) if denom else 1.0

    notes = []
    worth_it = expected_profit > 0
    if not worth_it:
        notes.append(f"Expected value is negative: you'd need a {break_even:.1%} win chance to break even.")
    if connects == 0:
        notes.append("0 Connects (invite) - always worth a reply if the client is legit.")

    boost_ok = (proposals or 0) >= 30 and connect_cost > 0 and contract_value / max(connect_cost, 0.01) > 200
    boost_budget = 0
    if boost_ok:
        # spend at most 1% of contract value on extra Connects, capped at 50
        boost_budget = int(min(50, max(0, (contract_value * 0.01) / connect_price)))
        notes.append(f"Crowded job ({proposals}+ proposals) with good value: boosting up to {boost_budget} extra Connects can pay off.")
    elif (proposals or 0) < 10:
        notes.append("Fewer than 10 proposals - boosting adds little; apply early instead.")

    return ConnectsROI(round(contract_value, 2), connects, round(connect_cost, 2), round(time_cost, 2),
                       round(win_probability, 4), round(expected_revenue, 2), round(expected_profit, 2),
                       round(roi, 2) if roi is not None else None, round(break_even, 4),
                       worth_it, boost_ok, boost_budget, notes)


def monthly_connects_budget(avg_connects_per_proposal: float, cold_proposals_per_month: int,
                            buffer: float = 0.2, connect_price: float = CONNECT_PRICE_USD) -> dict:
    needed = avg_connects_per_proposal * cold_proposals_per_month * (1 + buffer)
    bundles = [10, 20, 40, 60, 80]
    remaining, plan = needed, []
    while remaining > 0:
        b = next((x for x in bundles if x >= remaining), bundles[-1])
        plan.append(b)
        remaining -= b
    total = sum(plan)
    return {"connects_needed": round(needed), "suggested_bundles": plan, "connects_bought": total,
            "cost_usd": round(total * connect_price, 2), "keep_in_reserve": 60}
