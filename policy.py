"""The policy engine: one pure function that decides allow/deny.

Deliberately knows nothing about MCP, Kubernetes, AWS, or logging. That makes
it testable with plain pytest, with no server and no cluster running.

check() no longer hardcodes "namespace + resource" — it validates whatever
dimensions the caller passes in `values`, against a matching `allowed_<dim>s`
list in policy.yaml. A kubectl call passes {"namespace": ..., "resource": ...};
an AWS EC2 call passes {"region": ...}; a call with no dimensions to check
(aws_get_iam_policy) passes {} and is allowed as long as the tool itself is
in the allowlist. Same function, different backends.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

# Resolve relative to THIS file, not the working directory — an MCP server is
# launched as a child process by the host, often from a different cwd.
POLICY_PATH = Path(__file__).parent / "policy.yaml"
POLICY = yaml.safe_load(POLICY_PATH.read_text())


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


def check(tool_name: str, values: dict) -> Decision:
    """values: e.g. {"namespace": "dev", "resource": "pods"} or {"region": "ca-central-1"}
    or {} — whatever dimensions this tool declared in policy.yaml's `checks`."""
    spec = POLICY["tools"].get(tool_name)
    if spec is None:
        return Decision(False, f"tool '{tool_name}' is not in the allowlist")

    for dimension, value in values.items():
        allowlist_key = f"allowed_{dimension}s"
        allowlist = POLICY.get(allowlist_key)
        if allowlist is not None and value not in allowlist:
            return Decision(
                False,
                f"{dimension} '{value}' is not allowed; permitted {dimension}s are {allowlist}",
            )

    return Decision(True)