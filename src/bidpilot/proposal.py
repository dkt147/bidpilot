"""Proposal briefs and drafts.

BidPilot does not call an LLM itself. It builds a tight, evidence-based *brief* (the job's
real pain points, your best-matching proof, questions to ask, pitfalls to avoid) plus a
solid deterministic draft. When used through MCP, Claude (or any LLM client) turns the
brief into the final proposal in your voice. Nothing is ever submitted automatically.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .models import JobPost, PortfolioItem, Profile
from .scoring import skill_overlap

# (kind, pattern) - kind drives how the opening line is phrased
_PAIN_PATTERNS = [
    ("problem", r"(?:the )?(?:problem|issue|challenge|pain) is (?:that )?([^.\n]{10,240})"),
    ("need", r"(?:we|i) (?:need|want) (?:someone |somebody |a developer |an expert |help )?(?:to |who can |that can )([^.\n]{10,240})"),
    ("goal", r"(?:goal|objective|aim) is to ([^.\n]{10,240})"),
    ("seek", r"looking for (?:an |a |someone )?([^.\n]{10,240})"),
    ("must", r"(?:must|should) (?:be able to|have) ([^.\n]{10,200})"),
]
_QUESTION_HINTS = {
    "integration": "Which systems does this need to connect to, and do you already have API access?",
    "api": "Is there existing API documentation or credentials I can review?",
    "chatbot": "Where will the bot live (website, WhatsApp, Slack) and what should it hand off to a human?",
    "ai": "Do you have example data or documents the AI should learn from?",
    "automation": "What does the process look like today, step by step, and how often does it run?",
    "scrap": "Which sites/sources, how often, and what format do you need the output in?",
    "design": "Do you have brand guidelines or 2-3 examples you love?",
    "website": "Is there an existing site/hosting, or is this from scratch?",
    "app": "Which platforms (iOS, Android, web) and is there a design already?",
    "data": "Roughly how much data, and where does it live today?",
    "deadline": "Is the deadline fixed, or is there flexibility for a phased delivery?",
    "bug": "Can you share the exact error or steps to reproduce?",
}
_AVOID = [
    "Don't open with 'Dear Hiring Manager' or your name - open with their problem.",
    "Don't paste your full profile or skill list - 1-2 proofs beat 10 claims.",
    "Don't exceed ~150-200 words; clients read the first 2 lines in the preview.",
    "Don't promise exact timelines/prices before asking your key questions (unless fixed-price is clear).",
    "Don't use generic AI phrasing ('I am thrilled', 'I came across your job posting').",
]


@dataclass
class ProposalBrief:
    job_title: str
    pain_points: list[str]
    matched_skills: list[str]
    best_proof: list[dict]
    questions: list[str]
    suggested_rate: str
    structure: list[str]
    avoid: list[str]
    tone: str
    draft: str

    def to_dict(self) -> dict:
        return asdict(self)


def _tagged_pains(job: JobPost) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for kind, pat in _PAIN_PATTERNS:
        for m in re.finditer(pat, job.description, re.I):
            p = m.group(1).strip(" ,:;-")
            if p and p.lower() not in (x[1].lower() for x in found):
                found.append((kind, p))
    return found


def extract_pain_points(job: JobPost, limit: int = 4) -> list[str]:
    found = [p for _, p in _tagged_pains(job)]
    if not found:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", job.description) if 25 < len(s.strip()) < 180]
        found = sentences[:limit]
    return found[:limit]


_SWAP = {"our": "your", "ours": "yours", "we": "you", "us": "you", "my": "your", "i": "you",
         "we're": "you're", "we've": "you've", "i'm": "you're", "i've": "you've", "me": "you"}


def to_second_person(text: str) -> str:
    """'our front desk spends hours' -> 'your front desk spends hours'."""
    return re.sub(r"\b(our|ours|we're|we've|we|us|my|i'm|i've|i|me)\b",
                  lambda m: _SWAP[m.group(1).lower()], text, flags=re.I)


def opening_line(job: JobPost) -> str:
    """First line the client sees in the proposal preview - about THEIR problem, not you."""
    tagged = {k: to_second_person(v) for k, v in reversed(_tagged_pains(job))}  # first match of each kind wins
    if "problem" in tagged:
        p = tagged["problem"]
        return f"Hi - {p[0].lower() + p[1:]}. That's exactly the kind of problem I fix."
    if "need" in tagged:
        return f"Hi - I can help you {tagged['need']}."
    if "goal" in tagged:
        return f"Hi - I can help you {tagged['goal']}."
    if "seek" in tagged:
        return f"Hi - you're looking for {tagged['seek']}, and that's exactly what I do."
    return f"Hi - I read your post about {job.title or 'this project'} and I've built very similar work."


def rank_portfolio(job: JobPost, profile: Profile, limit: int = 2) -> list[PortfolioItem]:
    text = (job.title + " " + job.description + " " + " ".join(job.skills)).lower()

    def score(item: PortfolioItem) -> float:
        s = sum(2 for sk in item.skills if sk.lower() in text)
        s += sum(0.3 for w in set(re.findall(r"[a-z]{4,}", (item.title + " " + item.summary).lower())) if w in text)
        return s + (1 if item.result else 0)

    ranked = sorted(profile.portfolio, key=score, reverse=True)
    return [p for p in ranked if score(p) > 0][:limit]


def pick_questions(job: JobPost, limit: int = 3) -> list[str]:
    text = (job.title + " " + job.description).lower()
    qs = [q for key, q in _QUESTION_HINTS.items() if key in text]
    if not qs:
        qs = ["What does a great result look like for you in the first two weeks?"]
    return qs[:limit]


def suggest_rate(job: JobPost, profile: Profile) -> str:
    if job.budget_type == "hourly":
        if job.budget_max and job.budget_max < profile.hourly_rate:
            return (f"Their cap is ${job.budget_max:.0f}/hr vs your ${profile.hourly_rate:.0f}/hr. "
                    f"Either bid ${profile.hourly_rate:.0f}/hr and justify it with proof, or skip.")
        target = min(profile.hourly_rate, job.budget_max) if job.budget_max else profile.hourly_rate
        return f"Bid ${target:.0f}/hr (inside their range, at your rate)."
    if job.budget_type == "fixed" and job.budget_max:
        if job.budget_max < profile.min_fixed_budget:
            return (f"Budget ${job.budget_max:,.0f} is below your ${profile.min_fixed_budget:,.0f} minimum - "
                    f"propose a smaller phase 1 for ${job.budget_max:,.0f}, or skip.")
        return f"Bid at the posted ${job.budget_max:,.0f}; offer milestones (e.g. 30/40/30)."
    return "No budget given - ask 1 scoping question first, then quote with 2 options (basic / recommended)."


def build_brief(job: JobPost, profile: Profile) -> ProposalBrief:
    pains = extract_pain_points(job)
    _, matched = skill_overlap(job, profile)
    proofs = rank_portfolio(job, profile)
    questions = pick_questions(job)
    rate = suggest_rate(job, profile)
    structure = [
        "Line 1-2: restate their core problem/outcome in their words (this is the preview they see).",
        "Line 3-4: one concrete proof - a similar project and its measurable result.",
        "Line 5-6: your 2-3 step plan for THIS job.",
        "Line 7: one or two sharp questions.",
        "Close: low-friction CTA (quick call or Loom) + name.",
    ]
    draft = render_draft(job, profile, pains, proofs, questions)
    return ProposalBrief(job.title, pains, matched, [asdict(p) for p in proofs], questions, rate,
                         structure, list(_AVOID), profile.tone, draft)


def render_draft(job: JobPost, profile: Profile, pains: list[str], proofs: list[PortfolioItem],
                 questions: list[str]) -> str:
    lines = [opening_line(job)]
    if proofs:
        p = proofs[0]
        res = f" - result: {p.result}" if p.result else ""
        link = f"\n{p.link}" if p.link else ""
        lines.append(f"\nA recent similar project: {p.title}. {p.summary[0].upper() + p.summary[1:]}{res}.{link}")
    lines.append("\nMy plan for you:")
    lines.append("1. Quick review of your current setup and goals (day 1)")
    lines.append("2. Build the core and share a working demo early")
    lines.append("3. Polish, hand over with docs, and support you after launch")
    if questions:
        lines.append("\nTwo quick questions:")
        lines.extend(f"- {q}" for q in questions[:2])
    lines.append("\nHappy to jump on a 10-minute call or send a short Loom walkthrough.")
    lines.append(f"\n{profile.signature or profile.name or ''}".rstrip())
    return "\n".join(lines).strip()
