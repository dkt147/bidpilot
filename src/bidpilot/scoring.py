"""Score a job 0-100 and give an APPLY / MAYBE / SKIP verdict with reasons.

Weights reflect what consistently predicts wins on Upwork: client quality and history,
low competition, applying early, budget fit with your rate, and skill match.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from .connects import ConnectsROI, connects_roi, estimate_contract_value
from .models import JobPost, Profile
from .redflags import PENALTY, RedFlag, check_job, risk_level

WEIGHTS = {"client": 30, "competition": 20, "freshness": 10, "budget_fit": 20, "skill_match": 20}


@dataclass
class JobScore:
    score: int
    verdict: str
    risk: str
    breakdown: dict[str, float]
    reasons: list[str]
    red_flags: list[dict]
    win_probability: float
    roi: Optional[dict]
    matched_skills: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9+#.]", "", s.lower())


def skill_overlap(job: JobPost, profile: Profile) -> tuple[float, list[str]]:
    mine = {_norm(s): s for s in profile.skills + profile.niches if s}
    if not mine:
        return 0.5, []
    haystack = (" ".join(job.skills) + " " + job.title + " " + job.description).lower()
    hay_norm = _norm(haystack)
    matched = [orig for key, orig in mine.items() if key and (key in hay_norm or orig.lower() in haystack)]
    wanted = len(job.skills) or 5
    return min(1.0, len(matched) / min(wanted, 5)), matched


def _client_score(job: JobPost, reasons: list[str], missing: list[str]) -> float:
    c, s = job.client, 0.0
    if c.payment_verified is True:
        s += 0.25
    elif c.payment_verified is None:
        missing.append("payment verification")
        s += 0.1
    if c.total_spent is not None:
        s += 0.3 * min(1.0, math.log10(1 + c.total_spent) / 5)       # $100k+ -> full marks
        if c.total_spent >= 10_000:
            reasons.append(f"Client has spent ${c.total_spent:,.0f}+ on Upwork.")
    else:
        missing.append("client total spent")
    if c.hire_rate is not None:
        s += 0.25 * (c.hire_rate / 100)
        if c.hire_rate >= 70:
            reasons.append(f"Strong {c.hire_rate:.0f}% hire rate.")
    else:
        missing.append("client hire rate")
        s += 0.08
    if c.rating is not None:
        s += 0.2 * max(0.0, (c.rating - 3) / 2)
    else:
        s += 0.06
    return min(1.0, s)


def _competition_score(job: JobPost, reasons: list[str], missing: list[str]) -> float:
    if job.proposals_max is None and job.proposals_min is None:
        missing.append("proposal count")
        return 0.5
    p = job.proposals_max if job.proposals_max is not None else job.proposals_min
    s = 1.0 if p <= 5 else 0.85 if p <= 10 else 0.6 if p <= 20 else 0.35 if p <= 50 else 0.15
    if (job.interviewing or 0) >= 3:
        s *= 0.6
        reasons.append(f"Already interviewing {job.interviewing} freelancers.")
    if p <= 10:
        reasons.append(f"Low competition (<= {p} proposals).")
    return s


def _freshness_score(job: JobPost, reasons: list[str], missing: list[str]) -> float:
    h = job.posted_hours_ago
    if h is None:
        missing.append("posting time")
        return 0.5
    if h <= 1:
        reasons.append("Posted within the last hour - early bids win more often.")
        return 1.0
    return 0.9 if h <= 6 else 0.7 if h <= 24 else 0.4 if h <= 72 else 0.15


def _budget_fit(job: JobPost, profile: Profile, reasons: list[str], missing: list[str]) -> float:
    if job.budget_type == "hourly" and job.budget_max:
        ratio = job.budget_max / max(profile.hourly_rate, 1)
        if ratio < 0.7:
            reasons.append(f"Hourly cap ${job.budget_max:.0f} is well below your ${profile.hourly_rate:.0f}/hr.")
        return max(0.0, min(1.0, ratio))
    if job.budget_type == "fixed" and job.budget_max:
        if job.budget_max < profile.min_fixed_budget:
            reasons.append(f"Fixed budget ${job.budget_max:,.0f} is under your ${profile.min_fixed_budget:,.0f} minimum.")
            return max(0.0, job.budget_max / profile.min_fixed_budget * 0.6)
        return min(1.0, 0.6 + 0.4 * math.log10(job.budget_max / profile.min_fixed_budget + 1))
    missing.append("budget")
    return 0.5


def win_probability(base_rate: float, score_0_1: float) -> float:
    """Scale your historic win rate by how good this job is (0.3x for poor, up to 2.5x for great)."""
    return min(0.9, base_rate * (0.3 + 2.2 * score_0_1 ** 1.5))


def score_job(job: JobPost, profile: Optional[Profile] = None, est_hours: float = 40.0) -> JobScore:
    profile = profile or Profile()
    reasons: list[str] = []
    missing: list[str] = []

    skill, matched = skill_overlap(job, profile)
    if matched:
        reasons.append(f"Matches your skills: {', '.join(matched[:6])}.")
    elif profile.skills:
        reasons.append("No overlap with your listed skills.")

    parts = {
        "client": _client_score(job, reasons, missing),
        "competition": _competition_score(job, reasons, missing),
        "freshness": _freshness_score(job, reasons, missing),
        "budget_fit": _budget_fit(job, profile, reasons, missing),
        "skill_match": skill,
    }
    raw = sum(WEIGHTS[k] * v for k, v in parts.items())

    flags: list[RedFlag] = check_job(job)
    text_low = (job.title + " " + job.description).lower()
    flags_penalty = sum(PENALTY[f.severity] for f in flags)
    avoid_hits = [k for k in profile.avoid_keywords if k and k.lower() in text_low]
    if avoid_hits:
        flags_penalty += 15
        reasons.append(f"Contains keywords you avoid: {', '.join(avoid_hits)}.")

    score = int(round(max(0.0, min(100.0, raw - flags_penalty))))
    risk = risk_level(flags)
    if risk == "scam-likely":
        verdict = "SKIP"
        reasons.insert(0, "Scam indicators found - do not apply, consider reporting the post.")
    else:
        verdict = "APPLY" if score >= 65 else "MAYBE" if score >= 45 else "SKIP"

    p_win = 0.0 if risk == "scam-likely" else win_probability(profile.win_rate_estimate, score / 100)
    roi: Optional[ConnectsROI] = None
    value = estimate_contract_value(job.budget_type, job.budget_mid, est_hours)
    if value is not None:
        roi = connects_roi(value, job.connects_required or 0, p_win, profile.hourly_rate,
                           profile.hours_per_proposal, profile.profit_margin, job.proposals_max)
        if verdict == "APPLY" and not roi.worth_it:
            verdict = "MAYBE"
            reasons.append("Good job, but expected value doesn't cover Connects + time.")

    return JobScore(score, verdict, risk, {k: round(v * WEIGHTS[k], 1) for k, v in parts.items()},
                    reasons, [f.to_dict() for f in flags], round(p_win, 4),
                    roi.to_dict() if roi else None, matched, sorted(set(missing)))
