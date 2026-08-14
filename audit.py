"""Append-only audit trail. Every decision is recorded, allowed or denied."""

import datetime
import json
from pathlib import Path

AUDIT_PATH = Path(__file__).parent / "audit.log"


def log(tool: str, namespace: str, resource: str, decision) -> None:
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tool": tool,
        "namespace": namespace,
        "resource": resource,
        "allowed": decision.allowed,
        "reason": decision.reason,
    }
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")