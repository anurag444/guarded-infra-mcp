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

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from audit import log
from policy import POLICY, check


class PolicyMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name = context.message.name
        args = context.message.arguments or {}

        spec = POLICY["tools"].get(tool_name)
        if spec is None:
            # Unknown tool: deny before we even try to read its arguments.
            raise ToolError(f"DENIED: tool '{tool_name}' is not in the allowlist")

        # Build the dict of dimensions THIS tool cares about, per its own
        # `checks` declaration — never a fixed namespace/resource assumption.
        values = {}
        for dimension, rule in spec.get("checks", {}).items():
            if "from_arg" in rule:
                values[dimension] = args.get(rule["from_arg"], "")
            elif "fixed" in rule:
                values[dimension] = rule["fixed"]

        decision = check(tool_name, values)
        log(tool_name, values, decision)

        if not decision.allowed:
            # ToolError sends the reason back to the model instead of a result,
            # so the agent can read it and stop rather than retrying blindly.
            raise ToolError(f"DENIED: {decision.reason}")

        return await call_next(context)