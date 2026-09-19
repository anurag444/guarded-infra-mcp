"""Runs every eval case through the real gate and classifies the outcome.

DESIGN — L1, deterministic, no LLM
----------------------------------
Cases are driven through fastmcp's in-process Client, which is the same
protocol path a real host uses — so PolicyMiddleware.on_call_tool fires
exactly as it would in production. No subprocess, no network, no model.

Classification is deliberately narrow:

  blocked  = a ToolError whose message starts with "DENIED:"
  allowed  = anything else, INCLUDING backend failures

That second half is what makes this runnable with no cluster and no AWS
credentials. A call that passes the gate then hits a dead k8s API is still
`allowed` — the gate let it through, which is the only thing being measured
here. Mocking the backends would add machinery without adding signal.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml
from fastmcp import Client
from fastmcp.exceptions import ToolError

CASES_DIR = Path(__file__).parent / "cases"


@dataclass
class CaseResult:
    id: str
    category: str
    suite: str          # "attacks" or "legit"
    expected: str       # "blocked" or "allowed"
    actual: str         # "blocked" or "allowed"
    detail: str         # the DENIED reason, or the downstream error

    @property
    def correct(self) -> bool:
        return self.expected == self.actual


def load_cases(suite: str) -> list[dict]:
    path = CASES_DIR / f"{suite}.yaml"
    return yaml.safe_load(path.read_text())


async def classify(client: Client, tool: str, args: dict) -> tuple[str, str]:
    """One call through the real gate -> ("blocked"|"allowed", detail).

    Shared with the trajectory grader so both suites agree on what a denial
    is: a DENIED: ToolError from the middleware, and nothing else.
    """
    try:
        result = await client.call_tool(tool, args)
        return "allowed", f"returned: {result.data}"
    except ToolError as e:
        msg = str(e)
        if msg.startswith("DENIED:"):
            return "blocked", msg
        # A ToolError that isn't ours — e.g. the tool ran and raised.
        # The gate still let it through, so it counts as allowed.
        return "allowed", f"tool error (past the gate): {msg}"
    except Exception as e:
        # Schema/validation rejection or backend failure — also past our gate,
        # or never reached it. Either way, not a policy denial.
        return "allowed", f"{type(e).__name__}: {e}"


async def run_case(client: Client, case: dict, suite: str) -> CaseResult:
    actual, detail = await classify(client, case["tool"], case["args"])

    return CaseResult(
        id=case["id"],
        category=case.get("category", "uncategorised"),
        suite=suite,
        expected=case["expect"],
        actual=actual,
        detail=detail,
    )


async def run_all(mcp) -> list[CaseResult]:
    results = []
    async with Client(mcp) as client:
        for suite in ("attacks", "legit"):
            for case in load_cases(suite):
                results.append(await run_case(client, case, suite))
    return results