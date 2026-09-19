"""Asserts the audit line is queryable, not just written.

The value of the audit trail is that a question like "what did this agent try
that we refused?" is answerable with one jq expression. That only holds if
every line parses as JSON on its own, carries the same key set, and classifies
its denial in a machine-readable field. These tests pin exactly that.
"""

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from audit import AUDIT_PATH
from server import mcp

REQUIRED_KEYS = {
    "ts", "trace_id", "seq", "request_id", "tool",
    "allowed", "decision", "deny_category", "reason", "latency_ms", "outcome",
}


@pytest.fixture
def fresh_log():
    AUDIT_PATH.unlink(missing_ok=True)
    yield AUDIT_PATH
    AUDIT_PATH.unlink(missing_ok=True)


def read(path: Path) -> list[dict]:
    """Every line must parse standalone — that is the whole JSONL contract."""
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.asyncio
async def test_denied_call_is_logged_with_a_machine_readable_category(fresh_log):
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_get", {"namespace": "kube-system", "resource_type": "pods"})

    entry, = read(fresh_log)
    assert REQUIRED_KEYS <= set(entry)
    assert entry["decision"] == "deny"
    assert entry["allowed"] is False
    assert entry["deny_category"] == "out_of_scope_namespace"
    assert entry["namespace"] == "kube-system"
    assert entry["latency_ms"] is None, "nothing ran, so there is no latency to report"
    assert entry["outcome"] == "denied"


@pytest.mark.asyncio
async def test_unlisted_tool_gets_its_own_category(fresh_log):
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_delete", {"namespace": "dev", "pod_name": "x"})

    entry, = read(fresh_log)
    assert entry["deny_category"] == "unlisted_tool"


@pytest.mark.asyncio
async def test_allowed_call_is_logged_once_with_latency(fresh_log):
    """No cluster here, so the body fails — the line must still say the gate
    allowed it, and distinguish 'we let it through' from 'it worked'."""
    async with Client(mcp) as c:
        try:
            await c.call_tool("kubectl_get", {"namespace": "dev", "resource_type": "pods"})
        except Exception:
            pass

    entry, = read(fresh_log)
    assert entry["decision"] == "allow"
    assert entry["deny_category"] == ""
    assert entry["outcome"] in {"ok", "error"}
    assert isinstance(entry["latency_ms"], float)


@pytest.mark.asyncio
async def test_one_session_shares_a_trace_id_and_increments_seq(fresh_log):
    """This is what makes the file readable as trajectories: calls from one
    agent run group under one trace_id, in the order they happened."""
    async with Client(mcp) as c:
        for ns in ("kube-system", "default", "kube-public"):
            with pytest.raises(ToolError):
                await c.call_tool("kubectl_get", {"namespace": ns, "resource_type": "pods"})

    entries = read(fresh_log)
    assert len({e["trace_id"] for e in entries}) == 1, "one session must be one trace"
    assert [e["seq"] for e in entries] == sorted(e["seq"] for e in entries)
    assert [e["namespace"] for e in entries] == ["kube-system", "default", "kube-public"]


@pytest.mark.asyncio
async def test_every_line_has_the_same_key_set_across_backends(fresh_log):
    """kubectl and AWS lines differ only in dimension keys — the fixed keys
    are identical, so a single query covers both backends."""
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("kubectl_get", {"namespace": "kube-system", "resource_type": "pods"})
        with pytest.raises(ToolError):
            await c.call_tool("aws_describe_instances", {"region": "eu-west-1"})

    k8s, aws = read(fresh_log)
    assert REQUIRED_KEYS <= set(k8s) and REQUIRED_KEYS <= set(aws)
    assert "namespace" in k8s and "region" in aws
    assert k8s["deny_category"] == "out_of_scope_namespace"
    assert aws["deny_category"] == "out_of_scope_region"
