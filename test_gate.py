"""Gate tests: prove the policy layer actually blocks calls.

WHY THIS FILE EXISTS
--------------------
Importing a tool and calling it directly bypasses the middleware entirely.
Middleware only fires on `on_call_tool`, which means a real MCP protocol call.
So a direct call like `await kubectl_get(namespace="kube-system")` SUCCEEDS
even though the gate would refuse it — which makes direct-call tests useless
as evidence that the gate works.

FastMCP's `Client(mcp)` connects to the server object in memory, over the real
protocol path, with no subprocess and no network. That means the middleware
fires, and denials come back as ToolError.

These tests need NO cluster: a denied call is refused before it ever reaches
Kubernetes, so nothing here talks to k3d.

Run with:  pytest test_gate.py -v
"""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp


@pytest.mark.asyncio
async def test_disallowed_namespace_is_denied():
    """kube-system is not in allowed_namespaces — the gate must refuse."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError) as exc:
            await c.call_tool("kubectl_get", {"namespace": "kube-system", "resource_type": "pods"})
    assert "namespace" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_secrets_are_denied():
    """`secrets` is deliberately absent from allowed_resources."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError) as exc:
            await c.call_tool("kubectl_get", {"namespace": "dev", "resource_type": "secrets"})
    assert "denied" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_logs_tool_is_gated_too():
    """Regression guard: kubectl_logs had no check at all before the middleware.
    This test fails loudly if the gate is ever removed or bypassed for one tool."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_logs", {"namespace": "kube-system", "pod_name": "anything"})


@pytest.mark.asyncio
async def test_describe_tool_is_gated_too():
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_describe", {"namespace": "kube-system", "pod_name": "anything"})


@pytest.mark.asyncio
async def test_missing_namespace_argument_fails_closed():
    """A missing argument must be REFUSED, not treated as permissive.
    This is the deny-by-default property, tested rather than assumed."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_logs", {"pod_name": "anything"})


@pytest.mark.asyncio
async def test_only_expected_tools_are_exposed():
    """If a new tool is registered, this fails — a deliberate prompt to add it
    to policy.yaml rather than shipping it ungoverned."""
    async with Client(mcp) as c:
        names = {t.name for t in await c.list_tools()}
    assert names == {"kubectl_get", "kubectl_logs", "kubectl_describe"}