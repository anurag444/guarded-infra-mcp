"""The single gate.

`on_call_tool` fires on EVERY tool call before the tool body runs. Not calling
`call_next()` short-circuits the request, so the tool never executes. Add a new
tool to server.py — kubectl, AWS, or anything else — and it is gated
automatically as soon as it has a `tools:` entry in policy.yaml.

This middleware is deliberately generic: it doesn't know what "namespace" or
"region" mean. It just reads each tool's declared `checks` from policy.yaml,
pulls those specific argument values out of the raw call, and hands them to
check(). That's what makes "one gate, two backends" true in code, not just
in the README.
"""

import time

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from audit import log
from policy import POLICY, check


class PolicyMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name = context.message.name
        args = context.message.arguments or {}

        # Session id groups every call of one agent run under a single
        # trace_id, which is what turns the audit file into trajectories
        # rather than a flat list of unrelated decisions.
        ctx = context.fastmcp_context
        ids = {
            "trace_id": getattr(ctx, "session_id", None),
            "request_id": str(getattr(ctx, "request_id", None)) if ctx else None,
        }

        spec = POLICY["tools"].get(tool_name)
        if spec is None:
            # Unknown tool: deny before we even try to read its arguments —
            # but audit it first. An agent reaching for a tool that was never
            # registered is the single most interesting line in the file, and
            # it used to be the one event that left no trace.
            decision = check(tool_name, {})
            log(tool_name, {}, decision, outcome="denied", **ids)
            raise ToolError(f"DENIED: {decision.reason}")

        # Build the dict of dimensions THIS tool cares about, per its own
        # `checks` declaration — never a fixed namespace/resource assumption.
        values = {}
        for dimension, rule in spec.get("checks", {}).items():
            if "from_arg" in rule:
                values[dimension] = args.get(rule["from_arg"], "")
            elif "fixed" in rule:
                values[dimension] = rule["fixed"]

        decision = check(tool_name, values)

        if not decision.allowed:
            log(tool_name, values, decision, outcome="denied", **ids)
            # ToolError sends the reason back to the model instead of a result,
            # so the agent can read it and stop rather than retrying blindly.
            raise ToolError(f"DENIED: {decision.reason}")

        # Allowed calls are logged AFTER the body runs, so the line can carry
        # latency and whether the backend actually worked. A denial has neither
        # — nothing ran — which is why the two log sites are separate.
        started = time.perf_counter()
        try:
            result = await call_next(context)
        except Exception:
            log(tool_name, values, decision, outcome="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 2), **ids)
            raise
        log(tool_name, values, decision, outcome="ok",
            latency_ms=round((time.perf_counter() - started) * 1000, 2), **ids)
        return result