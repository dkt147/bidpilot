"""BidPilot command line.

  bidpilot analyze job.txt          score a pasted job (or pipe it: pbpaste | bidpilot analyze -)
  bidpilot brief job.txt            proposal brief + starter draft
  bidpilot flags message.txt        scam check on any text
  bidpilot roi 2000 16 --proposals 35
  bidpilot profile --rate 60 --skills "Python,FastAPI,n8n"
  bidpilot log "AI chatbot for clinic" --connects 16 --score 78
  bidpilot status 3 hired --value 2500
  bidpilot stats
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, storage
from .connects import connects_roi, monthly_connects_budget
from .parser import parse_job_text
from .proposal import build_brief
from .redflags import check_text, risk_level
from .scoring import score_job

C = {"APPLY": "\033[92m", "MAYBE": "\033[93m", "SKIP": "\033[91m", "end": "\033[0m", "dim": "\033[2m", "b": "\033[1m"}


def _color(s: str, key: str) -> str:
    return f"{C[key]}{s}{C['end']}" if sys.stdout.isatty() else s


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def _out(data, as_json: bool) -> bool:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    return as_json


def cmd_analyze(a):
    job = parse_job_text(_read(a.file))
    s = score_job(job, storage.load_profile(), a.hours)
    if _out(s.to_dict(), a.json):
        return
    bar = "█" * (s.score // 5) + "░" * (20 - s.score // 5)
    print(f"\n{_color(job.title[:80], 'b')}")
    print(f"Score  {bar} {s.score}/100   Verdict: {_color(s.verdict, s.verdict)}   Risk: {s.risk}")
    print(f"Win probability ≈ {s.win_probability:.1%}")
    print("\nBreakdown: " + ", ".join(f"{k} {v}" for k, v in s.breakdown.items()))
    for r in s.reasons:
        print(f"  • {r}")
    for f in s.red_flags:
        print(f"  ⚠ [{f['severity']}] {f['message']}" + (f"\n      {_color(f['evidence'], 'dim')}" if f["evidence"] else ""))
    if s.roi:
        r = s.roi
        print(f"\nConnects: {r['connects']} (${r['connect_cost']})  Expected profit ${r['expected_profit']}  "
              f"break-even win rate {r['break_even_win_rate']:.1%}")
        for n in r["notes"]:
            print(f"  → {n}")
    if s.missing_info:
        print(_color(f"\nMissing (paste the 'About the client' section for better accuracy): {', '.join(s.missing_info)}", "dim"))


def cmd_brief(a):
    b = build_brief(parse_job_text(_read(a.file)), storage.load_profile())
    if _out(b.to_dict(), a.json):
        return
    print(_color("\nPain points", "b"))
    for p in b.pain_points:
        print(f"  • {p}")
    print(_color("\nBest proof", "b"))
    for p in b.best_proof or [{"title": "(add portfolio items: bidpilot portfolio ...)"}]:
        print(f"  • {p['title']}")
    print(_color("\nQuestions to ask", "b"))
    for q in b.questions:
        print(f"  • {q}")
    print(_color("\nRate", "b") + f"\n  {b.suggested_rate}")
    print(_color("\nDraft", "b") + "\n" + b.draft + "\n")


def cmd_flags(a):
    flags = check_text(_read(a.file))
    if _out({"risk": risk_level(flags), "flags": [f.to_dict() for f in flags]}, a.json):
        return
    print(f"Risk: {risk_level(flags)}")
    for f in flags:
        print(f"  ⚠ [{f.severity}] {f.message}\n      {f.evidence}")


def cmd_roi(a):
    p = storage.load_profile()
    r = connects_roi(a.value, a.connects, a.win if a.win is not None else p.win_rate_estimate,
                     p.hourly_rate, p.hours_per_proposal, p.profit_margin, a.proposals)
    _out(r.to_dict(), True)


def cmd_budget(a):
    _out(monthly_connects_budget(a.avg, a.count), True)


def cmd_profile(a):
    changes = {"name": a.name, "headline": a.headline, "hourly_rate": a.rate, "min_fixed_budget": a.min_fixed,
               "tone": a.tone, "signature": a.signature, "win_rate_estimate": a.win_rate}
    if a.skills:
        changes["skills"] = [s.strip() for s in a.skills.split(",") if s.strip()]
    if a.niches:
        changes["niches"] = [s.strip() for s in a.niches.split(",") if s.strip()]
    if a.avoid:
        changes["avoid_keywords"] = [s.strip() for s in a.avoid.split(",") if s.strip()]
    p = storage.update_profile(**changes) if any(v is not None for v in changes.values()) else storage.load_profile()
    _out(p.to_dict(), True)


def cmd_portfolio(a):
    from .models import PortfolioItem
    p = storage.load_profile()
    p.portfolio.append(PortfolioItem(a.title, a.summary, [s.strip() for s in (a.skills or "").split(",") if s.strip()],
                                     a.result or "", a.link or ""))
    storage.save_profile(p)
    print(f"Added. You now have {len(p.portfolio)} portfolio items.")


def cmd_log(a):
    pid = storage.log_proposal(a.title, a.connects, a.score, a.url or "", a.niche or "", a.bid, "", a.boost)
    print(f"Logged proposal #{pid}")


def cmd_status(a):
    _out(storage.update_status(a.id, a.status, a.value, a.notes), True)


def cmd_list(a):
    for r in storage.list_proposals(a.status):
        print(f"#{r['id']:<4} {r['status']:<10} score {r['score'] if r['score'] is not None else '-':<4} "
              f"{r['connects']:>3} cx  {r['job_title'][:60]}")


def cmd_stats(a):
    _out(storage.pipeline_stats(), True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bidpilot", description="Upwork bidding copilot")
    p.add_argument("--version", action="version", version=f"bidpilot {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("analyze", help="score a job post (file path or - for stdin)")
    s.add_argument("file"); s.add_argument("--hours", type=float, default=40.0); s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_analyze)
    s = sub.add_parser("brief", help="proposal brief + draft")
    s.add_argument("file"); s.add_argument("--json", action="store_true"); s.set_defaults(func=cmd_brief)
    s = sub.add_parser("flags", help="scam check any text")
    s.add_argument("file"); s.add_argument("--json", action="store_true"); s.set_defaults(func=cmd_flags)
    s = sub.add_parser("roi", help="Connects ROI for one bid")
    s.add_argument("value", type=float, help="contract value $"); s.add_argument("connects", type=int)
    s.add_argument("--win", type=float); s.add_argument("--proposals", type=int); s.set_defaults(func=cmd_roi)
    s = sub.add_parser("budget", help="monthly Connects plan")
    s.add_argument("avg", type=float, help="avg Connects per proposal"); s.add_argument("count", type=int, help="cold proposals per month")
    s.set_defaults(func=cmd_budget)
    s = sub.add_parser("profile", help="show / update your profile")
    for flag in ("--name", "--headline", "--skills", "--niches", "--tone", "--signature", "--avoid"):
        s.add_argument(flag)
    s.add_argument("--rate", type=float); s.add_argument("--min-fixed", type=float); s.add_argument("--win-rate", type=float)
    s.set_defaults(func=cmd_profile)
    s = sub.add_parser("portfolio", help="add a portfolio proof point")
    s.add_argument("title"); s.add_argument("summary"); s.add_argument("--skills"); s.add_argument("--result"); s.add_argument("--link")
    s.set_defaults(func=cmd_portfolio)
    s = sub.add_parser("log", help="log a sent proposal")
    s.add_argument("title"); s.add_argument("--connects", type=int, default=0); s.add_argument("--boost", type=int, default=0)
    s.add_argument("--score", type=int); s.add_argument("--url"); s.add_argument("--niche"); s.add_argument("--bid", type=float)
    s.set_defaults(func=cmd_log)
    s = sub.add_parser("status", help="update a proposal status")
    s.add_argument("id", type=int); s.add_argument("status"); s.add_argument("--value", type=float); s.add_argument("--notes")
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("list", help="list proposals"); s.add_argument("--status"); s.set_defaults(func=cmd_list)
    s = sub.add_parser("stats", help="pipeline stats"); s.set_defaults(func=cmd_stats)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
