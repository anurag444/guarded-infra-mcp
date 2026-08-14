"""Tests for the policy gate.

No MCP server, no LLM, no cluster — `check()` is a pure function, so every
branch runs in milliseconds. This is the evidence that your gate works.

Run with:  pytest -v
"""

from policy import check


def test_allowed_call_passes():
    assert check("kubectl_get", "dev", "pods").allowed


def test_second_allowed_namespace_passes():
    assert check("kubectl_logs", "demo", "pods").allowed


def test_wrong_namespace_denied():
    d = check("kubectl_get", "kube-system", "pods")
    assert not d.allowed
    assert "namespace" in d.reason


def test_secrets_denied():
    d = check("kubectl_get", "dev", "secrets")
    assert not d.allowed
    assert "resource" in d.reason


def test_unknown_tool_denied():
    d = check("kubectl_delete", "dev", "pods")
    assert not d.allowed
    assert "allowlist" in d.reason


def test_empty_namespace_denied():
    # Guards the middleware's `args.get("namespace", "")` fallback: a missing
    # argument must fail closed, not sail through.
    assert not check("kubectl_get", "", "pods").allowed


def test_empty_resource_denied():
    assert not check("kubectl_logs", "dev", "").allowed