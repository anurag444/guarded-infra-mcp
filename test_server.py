"""Integration tests: the Kubernetes behaviour of each tool, against a live cluster.

SCOPE — read this before adding tests here
------------------------------------------
These call the tool functions DIRECTLY, which deliberately bypasses the policy
middleware (middleware only fires on real MCP protocol calls). That is the
right choice here: this file is about how each tool handles Kubernetes — empty
results, 404s, timeouts — not about whether the gate works.

The gate is covered separately in test_gate.py, which goes through the real
protocol path. Keep the split; a file that tries to do both proves neither.

ONE RULE: only use namespaces that appear in policy.yaml's allowed_namespaces.
A test against `default` or `kube-system` would pass here while being
unreachable in real use, which is worse than having no test at all.

Requires a running cluster:
    k3d cluster create guarded
    kubectl create namespace dev
    # NOTE: do NOT create `demo` — one test relies on it being absent.

Run with:      pytest test_server.py -v
Skip in CI:    pytest -m "not cluster"
"""

import asyncio

import pytest

from server import ResourceType, kubectl_describe, kubectl_get, kubectl_logs

pytestmark = pytest.mark.cluster


# ---------------------------------------------------------------------------
# 1. Schema/type validation — proving the Enum actually constrains input
# ---------------------------------------------------------------------------

def test_resource_type_rejects_invalid_value():
    """A resource_type outside the allowed set must be rejected, not silently accepted.

    NOTE: policy.yaml currently lists `deployments` and `services` under
    allowed_resources, but ResourceType only defines PODS — so the policy is
    more permissive than the code. Not a security hole (the code is the
    stricter of the two), but it is drift. See the note in the chat: either
    trim policy.yaml to `pods`, or add the enum members when you build
    those tools.
    """
    with pytest.raises(ValueError):
        ResourceType("deployments")


def test_resource_type_accepts_valid_value():
    """Sanity check the happy path isn't accidentally broken by the validation itself."""
    assert ResourceType("pods") == ResourceType.PODS


# ---------------------------------------------------------------------------
# 2. Not-found errors — the cluster is reachable, but the target doesn't exist
# ---------------------------------------------------------------------------

def test_kubectl_get_missing_namespace_returns_empty_not_crash():
    """Kubernetes' list API doesn't distinguish 'empty namespace' from
    'namespace doesn't exist' — both return an empty list. This documents
    that behaviour deliberately, rather than assuming a 404 that never comes.

    Uses `demo`: allowlisted in policy.yaml, but intentionally not created
    in the cluster, so this stays a reachable state rather than a fictional one.
    """
    result = asyncio.run(
        kubectl_get(namespace="demo", resource_type=ResourceType.PODS)
    )
    assert "error" not in result
    assert result["pods"] == []


def test_kubectl_logs_nonexistent_pod_returns_structured_error():
    """Same shape of error, different tool — proving the pattern is consistent
    across tools, not just correct for one of them."""
    result = asyncio.run(
        kubectl_logs(namespace="dev", pod_name="pod-that-does-not-exist")
    )
    assert "error" in result
    assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# 3. The genuine edge case — valid input, but a legitimately EMPTY result
# ---------------------------------------------------------------------------

def test_kubectl_get_empty_namespace_returns_empty_list_not_error():
    """An empty result is a VALID answer, not an error. This test protects
    against ever 'fixing' that into an incorrect error state.

    Assertion note: the original `== [] or isinstance(..., list)` could never
    fail — the second clause is true for any list, making the first redundant.
    Asserting the exact expected value is what actually catches a regression.
    """
    result = asyncio.run(
        kubectl_get(namespace="demo", resource_type=ResourceType.PODS)
    )
    assert "error" not in result
    assert result["pods"] == []


# ---------------------------------------------------------------------------
# 4. Consistency across tools — same error shape everywhere
# ---------------------------------------------------------------------------

def test_pod_targeted_tools_share_the_same_error_shape():
    """kubectl_logs and kubectl_describe both target a specific named pod,
    so both should 404 identically. kubectl_get is excluded — see the
    dedicated test above for why its behaviour is legitimately different."""
    bad_logs = asyncio.run(kubectl_logs(namespace="dev", pod_name="nope"))
    bad_describe = asyncio.run(kubectl_describe(namespace="dev", pod_name="nope"))

    for result in (bad_logs, bad_describe):
        assert "error" in result
        assert isinstance(result["error"], str)