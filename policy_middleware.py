"""The single gate.

`on_call_tool` fires on EVERY tool call before the tool body runs. Not calling
`call_next()` short-circuits the request, so the tool never executes. Add a new
tool to server.py and it is gated automatically — there is nothing to forget.
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

        namespace = args.get("namespace", "")

        # Either the resource is fixed for this tool, or it comes from an argument.
        if "resource_arg" in spec:
            resource = args.get(spec["resource_arg"], "")
        else:
            resource = spec.get("resource", "")

        decision = check(tool_name, namespace, resource)
        log(tool_name, namespace, resource, decision)

        if not decision.allowed:
            # ToolError sends the reason back to the model instead of a result,
            # so the agent can read it and stop rather than retrying blindly.
            raise ToolError(f"DENIED: {decision.reason}")

        return await call_next(context)