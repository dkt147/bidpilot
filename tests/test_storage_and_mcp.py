import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from bidpilot import storage

EX = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BIDPILOT_HOME", str(tmp_path))
    return tmp_path


def test_profile_roundtrip():
    p = storage.update_profile(name="Test", hourly_rate=80, skills=["Python"])
    assert storage.load_profile().hourly_rate == 80 and p.skills == ["Python"]


def test_pipeline():
    a = storage.log_proposal("Job A", connects=16, score=80, niche="ai")
    b = storage.log_proposal("Job B", connects=8, score=40, niche="web")
    storage.update_status(a, "hired", contract_value=2000)
    storage.update_status(b, "lost")
    s = storage.pipeline_stats()
    assert s["total_proposals"] == 2 and s["win_rate"] == 0.5
    assert s["connects_spent"] == 24 and s["revenue_won"] == 2000
    assert s["by_niche"]["ai"]["win_rate"] == 1.0
    assert "65+" in s["score_insight"]
    with pytest.raises(ValueError):
        storage.update_status(a, "nope")


def test_mcp_stdio_end_to_end(tmp_home):
    """Start the real server over stdio and call tools like Claude would."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "BIDPILOT_HOME": str(tmp_home),
           "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")}
    params = StdioServerParameters(command=sys.executable, args=["-m", "bidpilot.server"], env=env)

    def payload(result):
        sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
        if sc is not None:
            return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
        return json.loads(result.content[0].text)

    async def run():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                assert {"analyze_job", "rank_jobs", "proposal_brief", "check_red_flags",
                        "connects_calculator", "log_proposal", "pipeline_stats"} <= names
                prompts = {p.name for p in (await s.list_prompts()).prompts}
                assert {"write_proposal", "triage_jobs", "weekly_review"} <= prompts

                await s.call_tool("update_profile", {"skills": ["Python", "OpenAI", "RAG"], "hourly_rate": 55})
                res = payload(await s.call_tool("analyze_job", {"job_text": (EX / "good_job.txt").read_text()}))
                assert res["verdict"] == "APPLY"
                ranked = payload(await s.call_tool("rank_jobs", {"jobs": [
                    (EX / "scam_job.txt").read_text(), (EX / "good_job.txt").read_text()]}))
                assert ranked[0]["verdict"] == "APPLY" and ranked[-1]["risk"] == "scam-likely"

    asyncio.run(run())
