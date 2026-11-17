import json
from pathlib import Path

import pytest

from bidpilot import build_brief, check_text, connects_roi, job_from_dict, parse_job_text, score_job
from bidpilot.connects import monthly_connects_budget
from bidpilot.models import Profile

EX = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def profile():
    return Profile.from_dict(json.loads((EX / "profile.example.json").read_text()))


@pytest.fixture
def good():
    return parse_job_text((EX / "good_job.txt").read_text())


@pytest.fixture
def scam():
    return parse_job_text((EX / "scam_job.txt").read_text())


def test_parse_good_job(good):
    assert good.title.startswith("AI Chatbot")
    assert good.budget_type == "hourly" and good.budget_min == 40 and good.budget_max == 70
    assert good.experience_level == "intermediate"
    assert (good.proposals_min, good.proposals_max) == (5, 10)
    assert good.connects_required == 14
    assert good.posted_hours_ago == 2
    assert good.invites_sent == 2 and good.interviewing == 0
    c = good.client
    assert c.payment_verified is True
    assert c.rating == 4.9 and c.reviews == 37
    assert c.total_spent == 48_000 and c.hire_rate == 85
    assert c.jobs_posted == 42 and c.open_jobs == 1
    assert c.avg_hourly_paid == 45.2 and c.member_since == 2019
    assert "FastAPI" in good.skills


def test_parse_scam_job(scam):
    assert scam.budget_type == "fixed" and scam.budget_max == 1000
    assert scam.client.payment_verified is False
    assert scam.client.open_jobs == 6
    assert scam.posted_hours_ago == pytest.approx(20 / 60)


def test_good_job_scores_apply(good, profile):
    s = score_job(good, profile)
    assert s.verdict == "APPLY", s.to_dict()
    assert s.score >= 65
    assert s.risk in ("clean", "caution")
    assert "Python" in s.matched_skills
    assert s.roi["worth_it"] is True


def test_scam_job_is_skipped(scam, profile):
    s = score_job(scam, profile)
    assert s.verdict == "SKIP"
    assert s.risk == "scam-likely"
    codes = {f["code"] for f in s.red_flags}
    assert {"off_platform_contact", "off_platform_payment", "upfront_fee", "payment_unverified"} <= codes


def test_red_flags_text():
    assert check_text("Let's continue on WhatsApp, I'll pay you via Zelle")
    assert not check_text("Need a FastAPI backend with Postgres and tests. Milestones on Upwork.")


def test_connects_roi_and_boost():
    r = connects_roi(3000, 16, 0.1, hourly_rate=50, proposals=40)
    assert r.worth_it and r.boost_recommended and r.boost_max_connects > 0
    bad = connects_roi(50, 16, 0.02, hourly_rate=50)
    assert not bad.worth_it and bad.expected_profit < 0


def test_budget_plan():
    plan = monthly_connects_budget(12, 20)
    assert plan["connects_bought"] >= plan["connects_needed"] == 288


def test_brief_uses_portfolio(good, profile):
    b = build_brief(good, profile)
    assert b.pain_points
    assert b.best_proof and b.best_proof[0]["title"]
    assert b.questions
    assert "Daniyal" in b.draft
    assert "/hr" in b.suggested_rate


def test_job_from_dict_camelcase():
    job = job_from_dict({"title": "n8n workflow", "description": "Automate CRM sync",
                         "budgetType": "fixed", "budget": "$1,200", "proposalsMax": 15,
                         "connectsRequired": 12,
                         "client": {"paymentVerified": True, "totalSpent": "$25K", "hireRate": 70}})
    assert job.budget_type == "fixed" and job.budget_max == 1200
    assert job.proposals_max == 15 and job.connects_required == 12
    assert job.client.payment_verified and job.client.total_spent == 25000 and job.client.hire_rate == 70
