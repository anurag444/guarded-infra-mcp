"""A 60-second tour of the gate: four calls, then the audit trail.

Drives the real server over FastMCP's in-process client, so every call below
goes through PolicyMiddleware exactly as it would from Claude Code or VS Code.
Nothing here is simulated — the DENIED lines are the actual policy engine.
"""

import asyncio
import logging

from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp

# server.py configures INFO logging for real operation; the demo wants only
# the allow/deny lines on screen.
logging.getLogger().setLevel(logging.WARNING)

CALLS = [
    ("kubectl_get", {"namespace": "dev", "resource_type": "pods"},
     "allowlisted namespace + resource"),
    ("kubectl_get", {"namespace": "kube-system", "resource_type": "pods"},
     "cluster-operator namespace"),
    ("kubectl_get", {"namespace": "dev", "resource_type": "secrets"},
     "forbidden resource kind"),
    ("kubectl_delete", {"namespace": "dev", "pod_name": "app-123"},
     "tool never registered"),
]

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


async def main():
    async with Client(mcp) as c:
        for tool, args, note in CALLS:
            scope = " ".join(f"{k}={v}" for k, v in args.items())
            try:
                await c.call_tool(tool, args)
                print(f"{GREEN}ALLOW {OFF} {tool:<16} {scope:<38} {DIM}{note}{OFF}")
            except ToolError as e:
                msg = str(e)
                if msg.startswith("DENIED:"):
                    print(f"{RED}DENY  {OFF} {tool:<16} {scope:<38} {DIM}{note}{OFF}")
                    print(f"        {RED}{msg.removeprefix('DENIED: ')}{OFF}")
                else:
                    # Past the gate, failed in the backend — a different problem.
                    print(f"{GREEN}ALLOW {OFF} {tool:<16} {scope:<38} "
                          f"{DIM}(backend unavailable){OFF}")


if __name__ == "__main__":
    asyncio.run(main())
