"""Plain dataclasses shared by every BidPilot module."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class ClientStats:
    payment_verified: Optional[bool] = None
    rating: Optional[float] = None          # 0-5 stars
    reviews: Optional[int] = None
    total_spent: Optional[float] = None     # USD
    hire_rate: Optional[float] = None       # 0-100 %
    jobs_posted: Optional[int] = None
    open_jobs: Optional[int] = None
    hires: Optional[int] = None
    avg_hourly_paid: Optional[float] = None
    country: Optional[str] = None
    member_since: Optional[int] = None      # year


@dataclass
class JobPost:
    title: str = ""
    description: str = ""
    budget_type: Optional[str] = None       # "fixed" | "hourly"
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    experience_level: Optional[str] = None  # entry | intermediate | expert
    duration: Optional[str] = None
    proposals_min: Optional[int] = None
    proposals_max: Optional[int] = None
    interviewing: Optional[int] = None
    invites_sent: Optional[int] = None
    connects_required: Optional[int] = None
    posted_hours_ago: Optional[float] = None
    skills: list[str] = field(default_factory=list)
    client: ClientStats = field(default_factory=ClientStats)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def budget_mid(self) -> Optional[float]:
        if self.budget_min is None and self.budget_max is None:
            return None
        lo = self.budget_min if self.budget_min is not None else self.budget_max
        hi = self.budget_max if self.budget_max is not None else self.budget_min
        return (lo + hi) / 2


@dataclass
class PortfolioItem:
    title: str
    summary: str
    skills: list[str] = field(default_factory=list)
    result: str = ""                         # measurable outcome, e.g. "cut support tickets 40%"
    link: str = ""


@dataclass
class Profile:
    name: str = ""
    headline: str = ""
    hourly_rate: float = 50.0
    min_fixed_budget: float = 300.0
    skills: list[str] = field(default_factory=list)
    niches: list[str] = field(default_factory=list)
    portfolio: list[PortfolioItem] = field(default_factory=list)
    tone: str = "friendly, confident, concise"
    signature: str = ""
    avoid_keywords: list[str] = field(default_factory=list)
    win_rate_estimate: float = 0.10          # your historic cold-proposal win rate (0-1)
    profit_margin: float = 0.7               # share of contract value you keep after effort/fees
    hours_per_proposal: float = 0.3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        data = dict(data or {})
        data["portfolio"] = [p if isinstance(p, PortfolioItem) else PortfolioItem(**p)
                             for p in data.get("portfolio", [])]
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})
