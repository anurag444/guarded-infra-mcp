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

These tests need NO cluster and NO real AWS account: a denied call is refused
before it ever reaches Kubernetes or AWS, so nothing here talks to k3d or a
real AWS profile — server.py's session/client init must stay lazy for that
to hold (see the lru_cache note on load_k8s_client / get_aws_session).

Run with:  pytest test_gate.py -v
"""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp


# ---------------------------------------------------------------------------
# kubectl backend
# ---------------------------------------------------------------------------

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
    """Regression guard: kubectl_logs had no check at all before the middleware."""
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
    """A missing argument must be REFUSED, not treated as permissive."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_logs", {"pod_name": "anything"})


# ---------------------------------------------------------------------------
# AWS backend — same gate, different dimensions (region, not namespace)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disallowed_region_is_denied():
    """eu-west-1 is not in allowed_regions — the gate must refuse, same as
    an out-of-scope namespace does for kubectl."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError) as exc:
            await c.call_tool("aws_describe_instances", {"region": "eu-west-1"})
    assert "region" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_allowed_region_is_permitted():
    async with Client(mcp) as c:
        result = await c.call_tool("aws_describe_instances", {"region": "ca-central-1"})
    assert "reservations" in result.data


@pytest.mark.asyncio
async def test_missing_region_argument_fails_closed():
    """Same deny-by-default property as the kubectl namespace test, on the
    AWS side: an omitted region must be refused, not treated as unscoped."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("aws_describe_instances", {})


@pytest.mark.asyncio
async def test_iam_policy_tool_has_no_dimensions_to_check():
    """aws_get_iam_policy declares no `checks` in policy.yaml — it should
    still succeed, since being in the tools: allowlist is itself sufficient."""
    async with Client(mcp) as c:
        result = await c.call_tool(
            "aws_get_iam_policy", {"policy_arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"}
        )
    assert "policy" in result.data


@pytest.mark.asyncio
async def test_unregistered_aws_tool_is_denied():
    """A tool name that was never registered at all — distinct from a
    registered tool given a disallowed argument."""
    async with Client(mcp) as c:
        with pytest.raises(Exception):
            await c.call_tool("aws_terminate_instances", {"region": "ca-central-1"})


# ---------------------------------------------------------------------------
# Whole-server checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_only_expected_tools_are_exposed():
    """If a new tool is registered, this fails — a deliberate prompt to add it
    to policy.yaml rather than shipping it ungoverned. Updated for the AWS
    tools added this week; a 6th tool should trip this again."""
    async with Client(mcp) as c:
        names = {t.name for t in await c.list_tools()}
    assert names == {
        "kubectl_get", "kubectl_logs", "kubectl_describe",
        "aws_describe_instances", "aws_get_iam_policy",
    }


@pytest.mark.asyncio
async def test_audit_log_records_both_backends():
    """The concrete proof of 'one gate, two backends': a kubectl call and an
    AWS call, back to back, must both land in the same audit.log with the
    same shape (tool/allowed/reason), differing only in their dimension keys."""
    import json
    from pathlib import Path

    audit_path = Path(__file__).parent / "audit.log"
    audit_path.unlink(missing_ok=True)

    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_get", {"namespace": "kube-system", "resource_type": "pods"})
        with pytest.raises(ToolError):
            await c.call_tool("aws_describe_instances", {"region": "eu-west-1"})

    lines = [json.loads(l) for l in audit_path.read_text().splitlines()]
    tools_logged = {entry["tool"] for entry in lines}
    assert "kubectl_get" in tools_logged
    assert "aws_describe_instances" in tools_logged
    assert all("allowed" in entry and "reason" in entry for entry in lines)