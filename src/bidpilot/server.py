"""BidPilot MCP server - plug Upwork job intelligence into Claude or any MCP client.

Run:  bidpilot-mcp            (stdio, for Claude Desktop / Claude Code / Cursor)
      bidpilot-mcp --http     (streamable HTTP on :8000)

Works on its own (paste job posts) or next to Upwork's official MCP server
(https://mcp.upwork.com/mcp): fetch jobs there, judge them here. Upwork's server
intentionally does not score or rank jobs - BidPilot does, with your own data.
"""
from __future__ import annotations

import sys
from typing import Any, Optional

try:                                    # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                     # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import __version__, storage
from .connects import connects_roi as _roi
from .connects import monthly_connects_budget
from .models import PortfolioItem
from .parser import job_from_dict, parse_job_text
from .proposal import build_brief
from .redflags import check_text, risk_level
from .scoring import score_job

INSTRUCTIONS = """BidPilot is an Upwork bidding copilot for freelancers and agencies.
Typical flow: (1) get jobs - pasted by the user or from the official Upwork MCP's job search;
(2) call rank_jobs or analyze_job; (3) for APPLY jobs call proposal_brief and write the final
proposal in the user's voice using the brief; (4) after the user submits, call log_proposal;
(5) later update_proposal_status and use pipeline_stats for coaching.
Never tell the user to move communication or payment off Upwork. Never submit anything
yourself - the user always reviews and sends proposals."""

mcp = _Server("BidPilot", instructions=INSTRUCTIONS)


def _job(job_text: str = "", job: Optional[dict] = None):
    if job:
        return job_from_dict(job)
    if not job_text.strip():
        raise ValueError("Provide job_text (pasted job post) or job (structured dict).")
    return parse_job_text(job_text)


# ------------------------------------------------------------------ analysis
@mcp.tool()
def analyze_job(job_text: str = "", job: Optional[dict] = None, est_hours: float = 40.0) -> dict:
    """Score one Upwork job 0-100 and return APPLY / MAYBE / SKIP with reasons, scam red flags,
    win probability and Connects ROI, personalised with the saved freelancer profile.

    Pass either job_text (the whole job page pasted as text, including the 'About the client'
    section) or job (a dict such as one returned by the official Upwork MCP job search).
    est_hours: expected hours for hourly jobs, used to estimate contract value.
    """
    parsed = _job(job_text, job)
    result = score_job(parsed, storage.load_profile(), est_hours).to_dict()
    result["parsed_job"] = {k: v for k, v in parsed.to_dict().items() if k != "description"}
    return result


@mcp.tool()
def rank_jobs(jobs: list[Any], top: int = 10) -> list[dict]:
    """Rank many jobs at once (best first). Each item can be a pasted job string or a structured
    dict (e.g. from the official Upwork MCP search). Returns score, verdict, risk and top reasons."""
    out = []
    for i, item in enumerate(jobs):
        parsed = job_from_dict(item) if isinstance(item, dict) else parse_job_text(str(item))
        s = score_job(parsed, storage.load_profile())
        out.append({"index": i, "title": parsed.title[:120], "score": s.score, "verdict": s.verdict,
                    "risk": s.risk, "win_probability": s.win_probability,
                    "expected_profit": (s.roi or {}).get("expected_profit"),
                    "top_reasons": s.reasons[:3],
                    "url": item.get("url") if isinstance(item, dict) else None})
    return sorted(out, key=lambda r: r["score"], reverse=True)[:top]


@mcp.tool()
def check_red_flags(text: str) -> dict:
    """Scan any job post or client message for scam / bad-client patterns based on Upwork's own
    Trust & Safety guidance (off-platform contact or payment, upfront fees, free tests, gift cards,
    check fraud, account rental, sensitive data requests...)."""
    flags = check_text(text)
    return {"risk": risk_level(flags), "flags": [f.to_dict() for f in flags],
            "advice": "Keep all communication and payment on Upwork. Report scams via the flag on the job post."
            if flags else "No scam patterns detected in this text."}


@mcp.tool()
def connects_calculator(contract_value: float, connects: int, win_probability: Optional[float] = None,
                        proposals: Optional[int] = None) -> dict:
    """Is this bid worth the Connects? Returns expected revenue/profit, break-even win rate and
    whether boosting makes sense. win_probability defaults to the profile's historic win rate."""
    p = storage.load_profile()
    return _roi(contract_value, connects, win_probability if win_probability is not None else p.win_rate_estimate,
                p.hourly_rate, p.hours_per_proposal, p.profit_margin, proposals).to_dict()


@mcp.tool()
def connects_budget(avg_connects_per_proposal: float, cold_proposals_per_month: int) -> dict:
    """Plan how many Connects to buy this month (20% buffer for boosts) and which bundles."""
    return monthly_connects_budget(avg_connects_per_proposal, cold_proposals_per_month)


# ------------------------------------------------------------------ proposals
@mcp.tool()
def proposal_brief(job_text: str = "", job: Optional[dict] = None) -> dict:
    """Build an evidence-based proposal brief: the client's pain points, the freelancer's best
    matching portfolio proof, sharp questions, a rate suggestion, a proven structure, things to
    avoid, and a starter draft. Use it to write the final proposal in the user's voice
    (aim for 120-200 words; the first two lines are what the client sees in the preview)."""
    parsed = _job(job_text, job)
    brief = build_brief(parsed, storage.load_profile()).to_dict()
    brief["score"] = score_job(parsed, storage.load_profile()).to_dict()
    return brief


# ------------------------------------------------------------------ profile
@mcp.tool()
def get_profile() -> dict:
    """Return the saved freelancer profile used for scoring and proposals."""
    return storage.load_profile().to_dict()


@mcp.tool()
def update_profile(name: Optional[str] = None, headline: Optional[str] = None,
                   hourly_rate: Optional[float] = None, min_fixed_budget: Optional[float] = None,
                   skills: Optional[list[str]] = None, niches: Optional[list[str]] = None,
                   tone: Optional[str] = None, signature: Optional[str] = None,
                   avoid_keywords: Optional[list[str]] = None, win_rate_estimate: Optional[float] = None,
                   profit_margin: Optional[float] = None, hours_per_proposal: Optional[float] = None) -> dict:
    """Create or update the freelancer profile (only the fields you pass are changed).
    Tip: the official Upwork MCP can read the user's Upwork profile to fill this in."""
    return storage.update_profile(**{k: v for k, v in locals().items()}).to_dict()


@mcp.tool()
def add_portfolio_item(title: str, summary: str, skills: Optional[list[str]] = None,
                       result: str = "", link: str = "") -> dict:
    """Add a portfolio proof point. A measurable result (e.g. 'cut response time 60%') makes
    proposals far more convincing."""
    p = storage.load_profile()
    p.portfolio.append(PortfolioItem(title, summary, skills or [], result, link))
    storage.save_profile(p)
    return {"portfolio_items": len(p.portfolio), "added": title}


# ------------------------------------------------------------------ pipeline
@mcp.tool()
def log_proposal(job_title: str, connects: int = 0, score: Optional[int] = None, job_url: str = "",
                 niche: str = "", bid_amount: Optional[float] = None, budget_type: str = "",
                 boosted_connects: int = 0, notes: str = "") -> dict:
    """Record a proposal the user has sent, so win rates and Connects ROI can be tracked."""
    pid = storage.log_proposal(job_title, connects, score, job_url, niche, bid_amount, budget_type,
                               boosted_connects, notes)
    return {"id": pid, "status": "sent"}


@mcp.tool()
def update_proposal_status(proposal_id: int, status: str, contract_value: Optional[float] = None,
                           notes: Optional[str] = None) -> dict:
    """Move a proposal through the pipeline: sent, viewed, replied, interview, hired, lost, withdrawn.
    Pass contract_value when hired."""
    return storage.update_status(proposal_id, status, contract_value, notes)


@mcp.tool()
def list_proposals(status: Optional[str] = None, limit: int = 50) -> list[dict]:
    """List tracked proposals, newest first, optionally filtered by status."""
    return storage.list_proposals(status, limit)


@mcp.tool()
def pipeline_stats() -> dict:
    """Reply / interview / win rates, Connects spent, cost per win, revenue per Connect and
    performance by niche - the numbers that show where bidding effort pays off."""
    return storage.pipeline_stats()


# ------------------------------------------------------------------ resources & prompts
@mcp.resource("bidpilot://profile", name="profile", description="Saved freelancer profile",
              mime_type="application/json")
def profile_resource() -> str:
    import json
    return json.dumps(storage.load_profile().to_dict(), indent=2)


@mcp.prompt()
def write_proposal(job_text: str) -> str:
    """Analyse a job and write a winning proposal in my voice."""
    return ("Use BidPilot to help me bid on this Upwork job.\n"
            "1. Call analyze_job. If verdict is SKIP or risk is scam-likely, explain why in 3 bullets and stop.\n"
            "2. Otherwise call proposal_brief and write the final proposal (120-200 words) in my tone. "
            "The first two lines must speak to the client's problem. Use one proof from best_proof, "
            "a short plan, and the questions. No clichés, no 'Dear Hiring Manager'.\n"
            "3. Show the rate suggestion and Connects ROI in one line. Do not submit anything.\n\n"
            f"JOB:\n{job_text}")


@mcp.prompt()
def triage_jobs(search_query: str = "") -> str:
    """Find and triage today's best Upwork jobs (works with the official Upwork MCP)."""
    return ("Help me pick today's best Upwork jobs.\n"
            f"1. If the Upwork MCP is connected, search jobs for: {search_query or 'my profile skills'}. "
            "Otherwise ask me to paste job posts.\n"
            "2. Call BidPilot rank_jobs on the results.\n"
            "3. Show a table: rank, title, score, verdict, risk, expected profit.\n"
            "4. For the top 3 APPLY jobs, call proposal_brief and draft proposals for me to review. "
            "Never submit automatically.")


@mcp.prompt()
def weekly_review() -> str:
    """Weekly bidding review and coaching."""
    return ("Call BidPilot pipeline_stats and list_proposals. Give me a short weekly review: "
            "what's working by niche, where Connects are wasted, my reply and win rates versus last "
            "week if visible, and 3 specific changes for next week.")


def main(argv: Optional[list[str]] = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if "--version" in argv:
        print(f"bidpilot-mcp {__version__}")
        return
    mcp.run("streamable-http" if "--http" in argv else "stdio")


if __name__ == "__main__":
    main()
