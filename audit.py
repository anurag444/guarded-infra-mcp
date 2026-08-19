"""Append-only audit trail. Every decision is recorded, allowed or denied.

log() now takes a `values` dict instead of fixed namespace/resource
parameters, so one audit format covers kubectl calls, AWS calls, and
anything added later — the JSON shape differs only in which keys are
present, never in which function wrote it.
"""

import datetime
import json
from pathlib import Path

AUDIT_PATH = Path(__file__).parent / "audit.log"


def log(tool: str, values: dict, decision) -> None:
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tool": tool,
        **values,
        "allowed": decision.allowed,
        "reason": decision.reason,
    }
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")