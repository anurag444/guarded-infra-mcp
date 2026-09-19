"""Append-only audit trail: one JSON object per line, every decision, allowed
or denied.

WHY JSONL AND NOT A LOG STRING
------------------------------
The file is the evidence trail for "what did the agent try to do". That is
only useful if it is queryable without parsing prose, so every line is a
self-contained JSON object and the file is named .jsonl to say so. `jq` reads
it directly (see audit_queries.sh); so would Splunk, Loki, or a DuckDB
`read_json_auto` if this ever needs a real index behind it. Nothing about the
format is tied to a particular tool.

WHAT EACH LINE CARRIES
----------------------
  ts            UTC, ISO-8601
  trace_id      the MCP session — groups one agent's run into one trajectory
  seq           position within that run, so order survives log interleaving
  request_id    the individual call, for correlating with host-side logs
  tool          tool name
  <dimensions>  whatever the tool declared in policy.yaml (namespace,
                resource, region...) — flat, because which keys are present
                is itself the signal
  allowed       bool
  decision      "allow" | "deny" — the string form, for grouping in queries
  deny_category machine-readable reason class, "" when allowed. Set by the
                policy engine rather than regex'd back out of the message,
                so the prose can be reworded without breaking dashboards.
  reason        the human-readable message the agent saw
  latency_ms    wall time of the tool body, null on a denial (nothing ran)
  outcome       "denied" | "ok" | "error" — did the tool body succeed
"""

import datetime
import itertools
import json
import os
import uuid
from pathlib import Path

AUDIT_PATH = Path(__file__).parent / "audit.jsonl"

# Fallback trace id for calls that arrive without an MCP session (in-process
# test clients, direct invocation). Stable per process, so an eval run still
# groups into one trajectory instead of scattering across null.
_PROCESS_TRACE = f"proc-{os.getpid()}-{uuid.uuid4().hex[:8]}"
_seq = itertools.count(1)


def log(
    tool: str,
    values: dict,
    decision,
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    latency_ms: float | None = None,
    outcome: str = "denied",
) -> None:
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "trace_id": trace_id or _PROCESS_TRACE,
        "seq": next(_seq),
        "request_id": request_id,
        "tool": tool,
        **values,
        "allowed": decision.allowed,
        "decision": "allow" if decision.allowed else "deny",
        "deny_category": decision.category,
        "reason": decision.reason,
        "latency_ms": latency_ms,
        "outcome": outcome,
    }
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
