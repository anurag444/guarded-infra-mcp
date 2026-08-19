"""Tests for the policy gate.

No MCP server, no LLM, no cluster, no AWS account — check() is a pure
function, so every branch runs in milliseconds. This is the evidence that
your gate works, across both backends.

Run with:  pytest test_policy.py -v
"""

from policy import check


# ---------------------------------------------------------------------------
# kubectl-shaped calls — namespace + resource
# ---------------------------------------------------------------------------

def test_allowed_kubectl_call_passes():
    assert check("kubectl_get", {"namespace": "dev", "resource": "pods"}).allowed


def test_second_allowed_namespace_passes():
    assert check("kubectl_logs", {"namespace": "demo", "resource": "pods"}).allowed


def test_wrong_namespace_denied():
    d = check("kubectl_get", {"namespace": "kube-system", "resource": "pods"})
    assert not d.allowed
    assert "namespace" in d.reason


def test_secrets_denied():
    d = check("kubectl_get", {"namespace": "dev", "resource": "secrets"})
    assert not d.allowed
    assert "resource" in d.reason


def test_unknown_tool_denied():
    d = check("kubectl_delete", {"namespace": "dev", "resource": "pods"})
    assert not d.allowed
    assert "allowlist" in d.reason


def test_empty_namespace_denied():
    assert not check("kubectl_get", {"namespace": "", "resource": "pods"}).allowed


def test_empty_resource_denied():
    assert not check("kubectl_logs", {"namespace": "dev", "resource": ""}).allowed


# ---------------------------------------------------------------------------
# AWS-shaped calls — region only, or no dimensions at all
# ---------------------------------------------------------------------------

def test_allowed_region_passes():
    assert check("aws_describe_instances", {"region": "ca-central-1"}).allowed


def test_disallowed_region_denied():
    d = check("aws_describe_instances", {"region": "eu-west-1"})
    assert not d.allowed
    assert "region" in d.reason


def test_iam_policy_tool_needs_no_dimensions():
    # aws_get_iam_policy declares no checks in policy.yaml — an empty
    # values dict should still pass, since the tool itself IS allowlisted.
    assert check("aws_get_iam_policy", {}).allowed


def test_unknown_aws_tool_denied():
    d = check("aws_terminate_instances", {"region": "ca-central-1"})
    assert not d.allowed
    assert "allowlist" in d.reason