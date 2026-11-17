<div align="center">

# 🎯 BidPilot

### The Upwork bidding copilot for Claude and any MCP-compatible AI

**Stop wasting Connects.** BidPilot scores every Upwork job, catches scams before you bid, shows if a bid is worth the Connects, builds a proposal brief from *your* portfolio, and tracks your win rate. Use it as an **MCP server** in Claude, a **CLI**, or a **Python library**.

[![CI](https://github.com/dkt147/bidpilot/actions/workflows/ci.yml/badge.svg)](https://github.com/dkt147/bidpilot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-server-7f5af0)
![License](https://img.shields.io/badge/license-MIT-green)
![Privacy](https://img.shields.io/badge/data-100%25%20local-00c6ff)

</div>

---

## Why BidPilot?

Most freelancers close **under 5%** of proposals. Top agencies close **10–20%**. They don't send more proposals. They're pickier about which jobs they bid on, and they bid early. Each proposal costs **6–16 Connects at $0.15 each**, plus your time, and scam posts eat both.

Upwork launched an [official MCP server](https://www.upwork.com/ai/mcp) that lets AI agents search jobs and draft proposals. By design, that server **does not score, rank or choose jobs**. **BidPilot fills that gap**: it decides which jobs are worth bidding on and helps you win them.

| | Official Upwork MCP | **BidPilot** |
|---|:---:|:---:|
| Search jobs, read your profile, draft & submit proposals | ✅ | — *(use Upwork's)* |
| **Score & rank jobs 0–100 with reasons** | ❌ | ✅ |
| **Scam / bad-client detection** (Upwork Trust & Safety patterns) | ❌ | ✅ |
| **Connects ROI + boost advice** | ❌ | ✅ |
| **Proposal brief matched to your portfolio** | ❌ | ✅ |
| **Win-rate & cost-per-win tracking by niche** | ❌ | ✅ |
| Works without Upwork login / API approval | ❌ | ✅ |

They work well together. Upwork's MCP **fetches** the jobs, and BidPilot **judges** them.

---

## ✨ Features

- **🎯 Job scoring (0–100) → APPLY / MAYBE / SKIP.** The score weighs client quality (spend, hire rate, rating, payment verified), competition, how fresh the post is, budget fit with *your* rate, and skill match. Every verdict comes with plain-English reasons.
- **🚨 Scam & red-flag detection.** Flags off-platform contact or payment (Telegram, WhatsApp, PayPal, crypto), upfront fees, gift cards, check fraud, account rental, unpaid tests, sensitive-data requests, "$0 spent + many open jobs", low hire rate and history/budget mismatches. Every flag shows the matching evidence text.
- **💰 Connects economics.** Calculates expected profit, break-even win rate and whether to boost. It can also plan your monthly Connects bundles.
- **✍️ Proposal briefs.** Pulls the client's pain points, your best-matching portfolio proof, sharp questions, a rate suggestion, a proven structure and a starter draft. Claude turns the brief into a final proposal in your voice.
- **📈 Pipeline tracker.** Tracks reply, interview and win rates, Connects spent, cost per win and revenue per Connect. Results are split by niche, and it checks whether high-score jobs really do win more.
- **🔒 Private by design.** No scraping and no Upwork credentials. Everything is stored locally in `~/.bidpilot`, and nothing is ever submitted automatically.

---

## 🚀 Quick start

```bash
pip install git+https://github.com/dkt147/bidpilot.git
```

### Use with Claude Desktop

Add this to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "bidpilot": { "command": "bidpilot-mcp" }
  }
}
```

**Recommended:** also add Upwork's official server, so Claude can fetch jobs and BidPilot can judge them:

```json
{
  "mcpServers": {
    "bidpilot": { "command": "bidpilot-mcp" },
    "upwork":   { "command": "npx", "args": ["-y", "mcp-remote", "https://mcp.upwork.com/mcp"] }
  }
}
```

### Use with Claude Code

```bash
claude mcp add bidpilot -- bidpilot-mcp
```

### Use with Cursor, Windsurf, or other MCP clients

Point them at the `bidpilot-mcp` command over stdio. For HTTP clients, run `bidpilot-mcp --http`, which starts a streamable-HTTP server on port 8000.

### Then just ask Claude

> *"Set up my BidPilot profile: I'm a Python/FastAPI AI developer, $55/hr, I build RAG chatbots and n8n automations."*
>
> *"Here's a job, should I bid?"* (paste the whole job page, including **About the client**)
>
> *"Find today's best AI chatbot jobs on Upwork, rank them and draft proposals for the top 3."*
>
> *"I got hired on proposal #4 for $2,500. How's my win rate this month?"*

---

## 🧰 MCP tools

| Tool | What it does |
|---|---|
| `analyze_job` | Full score, verdict, risk, reasons, red flags, win probability and Connects ROI |
| `rank_jobs` | Rank a batch of pasted jobs, or job dicts from the Upwork MCP |
| `check_red_flags` | Scam check on any job post or client message |
| `proposal_brief` | Pain points, best proof, questions, rate, structure and draft |
| `connects_calculator` | Is this bid worth it? Should you boost? |
| `connects_budget` | Monthly Connects plan and bundles to buy |
| `get_profile` / `update_profile` | Your rate, skills, niches, tone and words to avoid |
| `add_portfolio_item` | Proof points with measurable results |
| `log_proposal` / `update_proposal_status` / `list_proposals` | Pipeline tracking |
| `pipeline_stats` | Reply, interview and win rates, cost per win, and results by niche |

**Prompts:** `write_proposal`, `triage_jobs`, `weekly_review`
**Resource:** `bidpilot://profile`

---

## 💻 CLI

```bash
bidpilot profile --name "Daniyal" --rate 55 --skills "Python,FastAPI,OpenAI,RAG,n8n"
bidpilot portfolio "Clinic chatbot" "RAG bot over FAQ + booking" --skills "RAG,OpenAI" --result "saved 3h/day"

pbpaste | bidpilot analyze -          # or: bidpilot analyze job.txt
bidpilot brief job.txt
bidpilot flags client_message.txt
bidpilot roi 3000 16 --proposals 40
bidpilot budget 12 20                 # avg Connects/proposal, proposals/month

bidpilot log "Clinic chatbot" --connects 14 --score 82 --niche ai-chatbots
bidpilot status 1 hired --value 2500
bidpilot stats
```

Example output:

```
AI Chatbot for Dental Clinic Website (RAG over our FAQ + booking)
Score  ██████████████████░░ 94/100   Verdict: APPLY   Risk: clean
Win probability ≈ 27.7%
  • Matches your skills: Python, FastAPI, OpenAI, RAG, n8n, Chatbot.
  • Client has spent $48,000+ on Upwork.
  • Strong 85% hire rate.
  • Low competition (<= 10 proposals).
Connects: 14 ($2.1)  Expected profit $407.36  break-even win rate 1.2%
```

Starter draft from `bidpilot brief`, opening with the client's problem in *their* words:

```
Hi - your front desk spends 3 hours a day answering the same questions. That's exactly the kind of problem I fix.

A recent similar project: E-commerce support agent. Voiceflow chatbot answering orders, returns and
shipping questions from a knowledge base, with voice - result: answers the most common support questions 24/7.
...
```

```
Simple Data Entry - Earn $500 per day...
Score  ░░░░░░░░░░░░░░░░░░░░ 0/100   Verdict: SKIP   Risk: scam-likely
  ⚠ [critical] Asks to move communication off Upwork ...
      ...please contact me on Telegram @fastjobs for details...
  ⚠ [critical] Mentions paying outside Upwork ...
  ⚠ [critical] Asks you to pay to get or start the job.
```

---

## 🐍 Python library

```python
from bidpilot import parse_job_text, score_job, build_brief, Profile

me = Profile(name="Daniyal", hourly_rate=55, skills=["Python", "OpenAI", "RAG"])
job = parse_job_text(open("job.txt").read())

result = score_job(job, me)
print(result.score, result.verdict, result.reasons)
print(build_brief(job, me).draft)
```

`job_from_dict()` accepts structured jobs in snake_case or camelCase, including a nested `client` object. That means you can feed it data from the Upwork MCP, the Upwork API or your own tools.

---

## 🧠 How scoring works

| Factor | Weight | Signals |
|---|---|---|
| Client quality | 30 | Payment verified, total spent (log-scaled), hire rate, rating |
| Competition | 20 | Proposal count, number already interviewing |
| Budget fit | 20 | Hourly cap vs your rate, fixed budget vs your minimum |
| Skill match | 20 | Overlap with your skills and niches |
| Freshness | 10 | Early bids win more; under 1 hour scores best |
| **Red flags** | penalty | Critical −60, high −25, medium −10, low −4. Any critical flag means SKIP |

Win probability is your historic win rate scaled by the job's score (0.3× for a poor job, up to 2.5× for a great one). The Connects ROI uses this formula:
`expected profit = contract value × win probability × margin − (Connects × $0.15 + proposal time × your rate)`.

All weights live in `src/bidpilot/scoring.py`, so you can tune them to your niche. After a few weeks of logging, `pipeline_stats` shows whether jobs scored 65+ really do win more for you.

---

## ✅ Responsible use

- BidPilot **never** scrapes Upwork, logs in or submits anything. You review and send every proposal yourself.
- It always recommends keeping communication and payment **on Upwork**, as Upwork's Terms of Service require.
- Red-flag rules follow Upwork's own guidance: [Upwork scams](https://www.upwork.com/resources/upwork-scams) and [client red flags](https://www.upwork.com/resources/client-red-flags).

## 🛠 Development

```bash
git clone https://github.com/dkt147/bidpilot && cd bidpilot
pip install -e ".[dev]"
pytest          # includes an end-to-end MCP stdio test
```

Works with MCP Python SDK 1.x (`FastMCP`) and 2.x (`MCPServer`).

## 🗺 Roadmap

- [ ] Saved-search alerts via the official Upwork MCP, with scheduled triage
- [ ] Per-niche weight auto-tuning from your own win history
- [ ] Agency mode (multiple freelancer profiles)
- [ ] Browser extension: one-click "Analyze this job"

## 👤 Author

Built by **[Daniyal Khan](https://github.com/dkt147)**, AI automation and full-stack developer.
Need a custom AI agent or automation? **[Hire me on Upwork](https://www.upwork.com/freelancers/~01fc7f8e0654357bd1)**.

MIT License. Not affiliated with or endorsed by Upwork Inc.
