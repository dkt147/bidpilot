"""Local storage: your profile (JSON) and a proposal pipeline tracker (SQLite).

Everything lives in ~/.bidpilot by default (override with the BIDPILOT_HOME env var).
No data leaves your machine.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Profile

STATUSES = ("sent", "viewed", "replied", "interview", "hired", "lost", "withdrawn")


def home() -> Path:
    p = Path(os.environ.get("BIDPILOT_HOME", Path.home() / ".bidpilot"))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- profile
def load_profile() -> Profile:
    f = home() / "profile.json"
    if f.exists():
        return Profile.from_dict(json.loads(f.read_text(encoding="utf-8")))
    return Profile()


def save_profile(profile: Profile) -> Path:
    f = home() / "profile.json"
    f.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
    return f


def update_profile(**changes) -> Profile:
    data = load_profile().to_dict()
    data.update({k: v for k, v in changes.items() if v is not None})
    profile = Profile.from_dict(data)
    save_profile(profile)
    return profile


# ---------------------------------------------------------------- tracker
_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_title TEXT NOT NULL,
    job_url TEXT,
    niche TEXT,
    score INTEGER,
    connects INTEGER DEFAULT 0,
    boosted_connects INTEGER DEFAULT 0,
    bid_amount REAL,
    budget_type TEXT,
    status TEXT DEFAULT 'sent',
    contract_value REAL,
    notes TEXT,
    sent_at TEXT,
    updated_at TEXT
);
"""


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(home() / "pipeline.db")
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_proposal(job_title: str, connects: int = 0, score: Optional[int] = None, job_url: str = "",
                 niche: str = "", bid_amount: Optional[float] = None, budget_type: str = "",
                 boosted_connects: int = 0, notes: str = "") -> int:
    with closing(_db()) as con, con:
        cur = con.execute(
            "INSERT INTO proposals (job_title, job_url, niche, score, connects, boosted_connects, bid_amount,"
            " budget_type, status, notes, sent_at, updated_at) VALUES (?,?,?,?,?,?,?,?, 'sent', ?, ?, ?)",
            (job_title, job_url, niche, score, connects, boosted_connects, bid_amount, budget_type, notes,
             _now(), _now()))
        return int(cur.lastrowid)


def update_status(proposal_id: int, status: str, contract_value: Optional[float] = None,
                  notes: Optional[str] = None) -> dict:
    status = status.lower()
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    with closing(_db()) as con, con:
        row = con.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise ValueError(f"No proposal with id {proposal_id}")
        con.execute("UPDATE proposals SET status=?, contract_value=COALESCE(?, contract_value),"
                    " notes=COALESCE(?, notes), updated_at=? WHERE id=?",
                    (status, contract_value, notes, _now(), proposal_id))
        return dict(con.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone())


def list_proposals(status: Optional[str] = None, limit: int = 50) -> list[dict]:
    with closing(_db()) as con:
        if status:
            rows = con.execute("SELECT * FROM proposals WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
        else:
            rows = con.execute("SELECT * FROM proposals ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


def pipeline_stats(connect_price: float = 0.15) -> dict:
    with closing(_db()) as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM proposals")]
    total = len(rows)
    if not total:
        return {"total_proposals": 0, "message": "No proposals logged yet. Use log_proposal after each bid."}

    def rate(statuses):
        return round(sum(r["status"] in statuses for r in rows) / total, 4)

    hired = [r for r in rows if r["status"] == "hired"]
    connects = sum((r["connects"] or 0) + (r["boosted_connects"] or 0) for r in rows)
    revenue = sum(r["contract_value"] or 0 for r in hired)
    by_niche: dict[str, dict] = {}
    for r in rows:
        n = r["niche"] or "other"
        b = by_niche.setdefault(n, {"proposals": 0, "hired": 0, "connects": 0})
        b["proposals"] += 1
        b["hired"] += r["status"] == "hired"
        b["connects"] += (r["connects"] or 0) + (r["boosted_connects"] or 0)
    for b in by_niche.values():
        b["win_rate"] = round(b["hired"] / b["proposals"], 4)

    scored = [r for r in rows if r["score"] is not None]
    hi = [r for r in scored if r["score"] >= 65]
    lo = [r for r in scored if r["score"] < 65]
    insight = None
    if hi and lo:
        hw = sum(r["status"] == "hired" for r in hi) / len(hi)
        lw = sum(r["status"] == "hired" for r in lo) / len(lo)
        insight = f"Jobs scored 65+ win {hw:.0%} vs {lw:.0%} below 65."

    return {
        "total_proposals": total,
        "reply_rate": rate({"replied", "interview", "hired"}),
        "interview_rate": rate({"interview", "hired"}),
        "win_rate": rate({"hired"}),
        "connects_spent": connects,
        "connects_cost_usd": round(connects * connect_price, 2),
        "revenue_won": round(revenue, 2),
        "cost_per_win_usd": round(connects * connect_price / len(hired), 2) if hired else None,
        "revenue_per_connect": round(revenue / connects, 2) if connects else None,
        "by_niche": by_niche,
        "score_insight": insight,
    }
