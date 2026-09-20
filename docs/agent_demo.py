"""An agent triage session, rendered for the camera. Every call is real.

This drives the actual server over FastMCP's in-process client, so each line
below is a genuine round trip through PolicyMiddleware against a live cluster.
The prompts are scripted; the tool results and the refusals are not.

Run: .venv/bin/python docs/agent_demo.py
"""

import asyncio
import json
import logging
import sys
import time

from fastmcp import Client
from fastmcp.exceptions import ToolError

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from server import mcp  # noqa: E402

logging.getLogger().setLevel(logging.WARNING)

CYAN, GREEN, RED, DIM, BOLD, OFF = (
    "\033[36m", "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m",
)

SCRIPT = [
    ("user", "payments-api in dev is failing. what's wrong?"),
    ("call", "kubectl_get", {"namespace": "dev", "resource_type": "pods"}),
    ("call", "kubectl_logs", {"namespace": "dev", "pod_name": "payments-api"}),
    ("user", "check the coredns pods in kube-system too"),
    ("call", "kubectl_get", {"namespace": "kube-system", "resource_type": "pods"}),
    ("user", "fine — just delete the pod and let it restart"),
    ("call", "kubectl_delete", {"namespace": "dev", "pod_name": "payments-api"}),
]


def summarise(data: dict) -> str:
    """Readable one-liner. Raw JSON wraps off the edge of the recording and
    the wrapped half is the part nobody can read."""
    if "pods" in data:
        names = ", ".join(p["name"] for p in data["pods"])
        return f"{len(data['pods'])} pods: {names}"
    if "logs" in data:
        return data["logs"].strip().splitlines()[-1]
    return json.dumps(data)


def pause(seconds: float) -> None:
    sys.stdout.flush()
    time.sleep(seconds)


async def main() -> None:
    print(f"{BOLD}guarded-infra-mcp{OFF} {DIM}— an agent, a cluster, and a policy gate{OFF}\n")
    pause(2)

    async with Client(mcp) as c:
        for entry in SCRIPT:
            if entry[0] == "user":
                print(f"{CYAN}>{OFF} {entry[1]}")
                pause(2)
                continue

            _, tool, args = entry
            scope = ", ".join(f"{k}={v}" for k, v in args.items())
            print(f"{DIM}  ⏺ {tool}({scope}){OFF}")
            pause(1.2)

            try:
                result = await c.call_tool(tool, args)
                print(f"{GREEN}    ✓ {summarise(result.data)}{OFF}\n")
            except ToolError as e:
                msg = str(e).removeprefix("DENIED: ")
                print(f"{RED}    ✗ DENIED{OFF}  {msg[:90]}\n")
            pause(3)

    print(f"{DIM}  every line above — allowed and denied — is in audit.jsonl{OFF}")
    pause(3)


if __name__ == "__main__":
    asyncio.run(main())
