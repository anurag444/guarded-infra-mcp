"""The policy engine: one pure function that decides allow/deny.

Deliberately knows nothing about MCP, Kubernetes, or logging. That makes it
testable with plain pytest, with no server and no cluster running.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

# Resolve relative to THIS file, not the working directory. An MCP server is
# launched as a child process by the host, often from a different cwd, so
# Path("policy.yaml") would silently fail to find the file.
POLICY_PATH = Path(__file__).parent / "policy.yaml"
POLICY = yaml.safe_load(POLICY_PATH.read_text())


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


def check(tool_name: str, namespace: str, resource: str) -> Decision:
    """Return Allow, or Deny with a reason the agent can read and act on."""
    if tool_name not in POLICY["tools"]:
        return Decision(False, f"tool '{tool_name}' is not in the allowlist")

    if namespace not in POLICY["allowed_namespaces"]:
        return Decision(
            False,
            f"namespace '{namespace}' is not allowed; "
            f"permitted namespaces are {POLICY['allowed_namespaces']}",
        )

    if resource not in POLICY["allowed_resources"]:
        return Decision(
            False,
            f"resource '{resource}' is not allowed; "
            f"permitted resources are {POLICY['allowed_resources']}",
        )

    return Decision(True)