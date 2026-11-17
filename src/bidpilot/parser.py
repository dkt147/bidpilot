"""Turn a job post copied from Upwork (or a dict from the official Upwork MCP) into a JobPost.

The parser is deliberately forgiving: Upwork changes its page layout often, so every
field is optional and extracted with independent patterns.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .models import ClientStats, JobPost

_MONEY = r"\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?"


def _money(num: str, suffix: Optional[str] = None) -> float:
    value = float(num.replace(",", ""))
    if suffix:
        value *= {"k": 1_000, "m": 1_000_000}[suffix.lower()]
    return value


def _search(pattern: str, text: str, flags: int = re.I) -> Optional[re.Match]:
    return re.search(pattern, text, flags)


def _int(pattern: str, text: str) -> Optional[int]:
    m = _search(pattern, text)
    return int(m.group(1).replace(",", "")) if m else None


def parse_budget(text: str, job: JobPost) -> None:
    hourly = _search(rf"{_MONEY}\s*(?:-|–|to)\s*{_MONEY}\s*(?:/\s*hr|per hour|hourly)", text) \
        or _search(rf"hourly[^\n$]{{0,40}}{_MONEY}\s*(?:-|–|to)\s*{_MONEY}", text)
    if hourly:
        job.budget_type = "hourly"
        job.budget_min = _money(hourly.group(1), hourly.group(2))
        job.budget_max = _money(hourly.group(3), hourly.group(4))
        return
    single_hourly = _search(rf"{_MONEY}\s*(?:/\s*hr|per hour)", text)
    if single_hourly:
        job.budget_type = "hourly"
        job.budget_min = job.budget_max = _money(single_hourly.group(1), single_hourly.group(2))
        return
    fixed = _search(rf"(?:fixed[- ]price|budget)\s*[:\-]?\s*{_MONEY}", text) \
        or _search(rf"{_MONEY}\s*\n?\s*fixed[- ]price", text)
    if fixed:
        job.budget_type = "fixed"
        job.budget_min = job.budget_max = _money(fixed.group(1), fixed.group(2))
    elif _search(r"\bhourly\b", text):
        job.budget_type = "hourly"


def parse_client(text: str) -> ClientStats:
    c = ClientStats()
    if _search(r"payment\s+(?:method\s+)?(?:not\s+verified|unverified)", text):
        c.payment_verified = False
    elif _search(r"payment\s+(?:method\s+)?verified", text):
        c.payment_verified = True

    m = _search(r"(\d(?:\.\d+)?)\s*(?:of 5|/\s*5|stars?)", text) or _search(r"rating\s*[:\-]?\s*(\d(?:\.\d+)?)", text)
    if m:
        c.rating = float(m.group(1))
    c.reviews = _int(r"(?<!of )(?<![\d.])([\d,]+)\s+reviews?", text)

    m = _search(rf"{_MONEY}\s*\+?\s*total\s+spent", text)
    if m:
        c.total_spent = _money(m.group(1), m.group(2))
    m = _search(r"(\d{1,3})\s*%\s*hire\s+rate", text)
    if m:
        c.hire_rate = float(m.group(1))
    c.jobs_posted = _int(r"([\d,]+)\s+jobs?\s+posted", text)
    c.open_jobs = _int(r"([\d,]+)\s+open\s+jobs?", text)
    c.hires = _int(r"([\d,]+)\s+hires?\b", text)
    m = _search(rf"{_MONEY}\s*/\s*hr\s+avg\s+hourly\s+rate\s+paid", text)
    if m:
        c.avg_hourly_paid = _money(m.group(1), m.group(2))
    m = _search(r"member\s+since\s+(?:[A-Za-z]+\s+\d{1,2},?\s+)?(\d{4})", text)
    if m:
        c.member_since = int(m.group(1))
    return c


def parse_job_text(text: str, title: str = "") -> JobPost:
    """Parse free text pasted from an Upwork job page."""
    text = text or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    job = JobPost(title=title or (lines[0] if lines else ""), description=text)

    parse_budget(text, job)

    for level in ("entry", "intermediate", "expert"):
        if _search(rf"\b{level}(?:\s+level)?\b", text):
            job.experience_level = level
            break

    m = _search(r"proposals?\s*[:\-]?\s*(\d+)\s*(?:to|-|–)\s*(\d+)", text)
    if m:
        job.proposals_min, job.proposals_max = int(m.group(1)), int(m.group(2))
    else:
        m = _search(r"proposals?\s*[:\-]?\s*(?:less than|fewer than)\s*(\d+)", text)
        if m:
            job.proposals_min, job.proposals_max = 0, int(m.group(1))
        else:
            m = _search(r"proposals?\s*[:\-]?\s*(\d+)\s*\+", text)
            if m:
                job.proposals_min = job.proposals_max = int(m.group(1))

    job.interviewing = _int(r"interviewing\s*[:\-]?\s*(\d+)", text)
    job.invites_sent = _int(r"invites?\s+sent\s*[:\-]?\s*(\d+)", text)
    job.connects_required = _int(r"(\d+)\s+connects", text) or _int(r"connects\s*(?:required)?\s*[:\-]?\s*(\d+)", text)

    m = _search(r"posted\s+(\d+|an?|one)\s+(minute|hour|day|week)s?\s+ago", text)
    if m:
        qty = 1 if m.group(1).lower() in ("a", "an", "one") else int(m.group(1))
        job.posted_hours_ago = qty * {"minute": 1 / 60, "hour": 1, "day": 24, "week": 168}[m.group(2).lower()]
    elif _search(r"posted\s+(?:just now|moments ago)", text):
        job.posted_hours_ago = 0.0
    elif _search(r"posted\s+yesterday", text):
        job.posted_hours_ago = 24.0

    m = _search(r"skills?(?:\s+and\s+expertise)?\s*[:\-]\s*(.+)", text)
    if m:
        job.skills = [s.strip() for s in re.split(r"[,;|•]", m.group(1)) if 1 < len(s.strip()) < 40]

    job.client = parse_client(text)
    return job


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(_MONEY, str(value))
    return _money(m.group(1), m.group(2)) if m else None


def job_from_dict(data: dict) -> JobPost:
    """Build a JobPost from structured data (e.g. results of the official Upwork MCP).

    Accepts common key spellings (snake_case and camelCase) and nested `client` dicts.
    Anything missing is filled by parsing `description`.
    """
    d = {re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): v for k, v in (data or {}).items()}
    text = str(d.get("description") or d.get("text") or "")
    job = parse_job_text(text, title=str(d.get("title") or ""))

    for key, attr in [("budget_type", "budget_type"), ("experience_level", "experience_level"),
                      ("duration", "duration")]:
        if d.get(key):
            setattr(job, attr, str(d[key]).lower())
    for key, attr in [("budget_min", "budget_min"), ("budget_max", "budget_max"),
                      ("hourly_min", "budget_min"), ("hourly_max", "budget_max")]:
        if _num(d.get(key)) is not None:
            setattr(job, attr, _num(d[key]))
    if _num(d.get("budget")) is not None and job.budget_min is None:
        job.budget_min = job.budget_max = _num(d["budget"])
        job.budget_type = job.budget_type or "fixed"
    for key in ("proposals_min", "proposals_max", "interviewing", "invites_sent",
                "connects_required", "posted_hours_ago"):
        if _num(d.get(key)) is not None:
            setattr(job, key, _num(d[key]) if key == "posted_hours_ago" else int(_num(d[key])))
    if d.get("skills"):
        job.skills = list(d["skills"]) if not isinstance(d["skills"], str) else \
            [s.strip() for s in d["skills"].split(",") if s.strip()]

    client = {re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): v for k, v in (d.get("client") or {}).items()}
    for key in ClientStats.__dataclass_fields__:
        if key in client and client[key] is not None:
            val = client[key]
            if key == "payment_verified":
                val = bool(val)
            elif key in ("country",):
                val = str(val)
            elif key in ("reviews", "jobs_posted", "open_jobs", "hires", "member_since"):
                val = int(_num(val))
            else:
                val = _num(val)
            setattr(job.client, key, val)
    return job
