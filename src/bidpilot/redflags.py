"""Scam and bad-client detection.

Rules are based on Upwork's own published guidance:
- https://www.upwork.com/resources/upwork-scams
- https://www.upwork.com/resources/client-red-flags
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional

from .models import JobPost

CRITICAL, HIGH, MEDIUM, LOW = "critical", "high", "medium", "low"
PENALTY = {CRITICAL: 60, HIGH: 25, MEDIUM: 10, LOW: 4}


@dataclass
class RedFlag:
    code: str
    severity: str
    message: str
    evidence: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# (code, severity, regex, explanation)
TEXT_RULES: list[tuple[str, str, str, str]] = [
    ("off_platform_contact", CRITICAL,
     r"\b(telegram|whats\s?app|signal app|wechat|skype me|text me at|contact me (?:at|on)|my (?:email|gmail) is|@gmail\.com|add me on)\b",
     "Asks to move communication off Upwork - the #1 scam pattern and against Upwork's Terms."),
    ("off_platform_payment", CRITICAL,
     r"\b(paypal|venmo|cash\s?app|zelle|wire transfer|western union|bank transfer|pay (?:you )?directly|outside (?:of )?upwork|crypto wallet|usdt|bitcoin)\b",
     "Mentions paying outside Upwork - you lose payment protection."),
    ("check_or_reimbursement", CRITICAL,
     r"\b(cashier'?s check|send (?:you )?a check|deposit (?:the )?check|reimburse(?:d|ment)?|buy (?:the )?(?:equipment|supplies) and)\b",
     "Check / reimbursement pattern used in overpayment fraud."),
    ("gift_cards", CRITICAL, r"\bgift\s?cards?\b", "Gift-card requests are always a scam."),
    ("upfront_fee", CRITICAL,
     r"\b(registration fee|training fee|pay (?:a |the )?(?:small )?fee|fee to (?:access|join|start)|purchase (?:our|the) (?:software|tool|kit)|starter kit)\b",
     "Asks you to pay to get or start the job."),
    ("sensitive_data", CRITICAL,
     r"\b(ssn|social security|bank account (?:number|details)|credit card (?:number|details)|passport (?:copy|scan)|id card (?:copy|scan)|your upwork (?:login|password|account access))\b",
     "Requests sensitive personal or account data."),
    ("account_rental", CRITICAL,
     r"\b(rent (?:your|an) (?:upwork )?account|use your (?:upwork )?account|account (?:rental|sharing)|bid on my behalf)\b",
     "Account rental / sharing is fraud and gets accounts banned."),
    ("social_engagement_task", HIGH,
     r"\b(like (?:videos|posts)|subscribe to (?:my|our) (?:youtube|channel)|join (?:our|my) (?:telegram|discord|whatsapp) group|boost engagement)\b",
     "Engagement-task scams usually start this way."),
    ("free_work", HIGH,
     r"\b(unpaid (?:test|trial|sample)|free (?:test|sample|trial task)|test task (?:before|prior to) (?:hiring|contract)|do (?:a|this) (?:small )?task for free)\b",
     "Asks for free work before a contract."),
    ("too_good_to_be_true", HIGH,
     r"\b(\$\s?\d{3,}\s*(?:per|/)\s*(?:day|hour) for (?:simple|easy)|no experience (?:needed|required).{0,40}(?:high|great) pay|earn \$\d{3,} (?:daily|per day))\b",
     "Unrealistically high pay for trivial work."),
    ("urgent_pressure", MEDIUM,
     r"\b(asap|urgent(?:ly)?|immediately|right now|within (?:the next )?\d+ (?:minutes|hours))\b",
     "High urgency - fine for real emergencies, but common in pressure scams and scope creep."),
    ("lowball", MEDIUM,
     r"\b(very (?:low|small|tight) budget|cheap(?:est)?|lowest (?:price|bid|rate)|budget is (?:very )?(?:low|limited))\b",
     "Client signals price is the top priority."),
    ("scope_creep_language", LOW,
     r"\b(and (?:more|other tasks)|ongoing small tasks|unlimited revisions|whatever (?:is|comes) needed|simple (?:app|website) like (?:uber|airbnb|facebook|amazon))\b",
     "Vague or unbounded scope."),
    ("ai_training_fee", HIGH,
     r"\b(ai (?:training|annotation) (?:job|task).{0,60}(?:fee|deposit|purchase))\b",
     "Fake AI-training jobs that later charge a fee."),
]


def _evidence(m: re.Match, text: str) -> str:
    start, end = max(0, m.start() - 40), min(len(text), m.end() + 40)
    return ("..." if start else "") + text[start:end].replace("\n", " ").strip() + ("..." if end < len(text) else "")


def check_text(text: str) -> list[RedFlag]:
    flags = []
    for code, sev, pattern, msg in TEXT_RULES:
        m = re.search(pattern, text or "", re.I)
        if m:
            flags.append(RedFlag(code, sev, msg, _evidence(m, text)))
    return flags


def check_job(job: JobPost, now_year: Optional[int] = None) -> list[RedFlag]:
    flags = check_text(f"{job.title}\n{job.description}")
    c = job.client

    if c.payment_verified is False:
        flags.append(RedFlag("payment_unverified", HIGH,
                             "Client payment method is not verified."))
    if (c.total_spent in (None, 0)) and (c.open_jobs or 0) >= 3:
        flags.append(RedFlag("many_open_jobs_no_spend", HIGH,
                             f"{c.open_jobs} open jobs but $0 spent - classic fake/phishing account pattern."))
    if c.hire_rate is not None and c.jobs_posted and c.jobs_posted >= 5 and c.hire_rate < 25:
        flags.append(RedFlag("low_hire_rate", MEDIUM,
                             f"Hire rate {c.hire_rate:.0f}% across {c.jobs_posted} jobs - often collects proposals without hiring."))
    if c.rating is not None and c.reviews and c.reviews >= 3 and c.rating < 4.0:
        flags.append(RedFlag("poor_client_rating", MEDIUM,
                             f"Client rating {c.rating:.1f}/5 from {c.reviews} reviews."))
    if c.avg_hourly_paid is not None and job.budget_type == "hourly" and job.budget_max \
            and job.budget_max > 3 * c.avg_hourly_paid and job.budget_max > 60:
        flags.append(RedFlag("budget_mismatch_history", MEDIUM,
                             f"Posted ${job.budget_max:.0f}/hr but historically pays ~${c.avg_hourly_paid:.0f}/hr."))
    if job.invites_sent is not None and job.invites_sent == 0 and (job.proposals_min or 0) >= 50 \
            and (job.interviewing or 0) == 0:
        flags.append(RedFlag("crowded_no_engagement", LOW,
                             "50+ proposals and nobody interviewed yet - low odds or inactive client."))
    if c.total_spent in (None, 0) and c.payment_verified is not True and not c.reviews:
        flags.append(RedFlag("brand_new_unverified_client", MEDIUM,
                             "Brand-new client with no spend, reviews, or verified payment."))

    order = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}
    return sorted(flags, key=lambda f: order[f.severity])


def risk_level(flags: list[RedFlag]) -> str:
    sev = {f.severity for f in flags}
    if CRITICAL in sev:
        return "scam-likely"
    if HIGH in sev:
        return "high-risk"
    if MEDIUM in sev:
        return "caution"
    return "clean"
