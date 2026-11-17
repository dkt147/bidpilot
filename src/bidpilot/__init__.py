"""BidPilot - Upwork bidding copilot with an MCP server for Claude and other AI tools."""
__version__ = "0.1.0"

from .models import ClientStats, JobPost, PortfolioItem, Profile  # noqa: E402
from .parser import job_from_dict, parse_job_text  # noqa: E402
from .redflags import check_job, check_text  # noqa: E402
from .scoring import score_job  # noqa: E402
from .proposal import build_brief  # noqa: E402
from .connects import connects_roi  # noqa: E402

__all__ = ["ClientStats", "JobPost", "PortfolioItem", "Profile", "job_from_dict", "parse_job_text",
           "check_job", "check_text", "score_job", "build_brief", "connects_roi", "__version__"]
