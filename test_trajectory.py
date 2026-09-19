"""Asserts the trajectory grader's headline numbers, and that it can fail.

The second half matters more than the first. A grader that never fails is
indistinguishable from no grader at all, so `grade()` is exercised directly
on hand-built call lists — one per axis — instead of only on fixtures that
are already expected to pass.
"""

import pytest

from evals.report import print_trajectory_report, score_trajectories
from evals.trajectory import grade, run_all_trajectories
from server import mcp

ALLOWED = ("allowed", "returned: {}")
BLOCKED = ("blocked", "DENIED: namespace 'kube-system' is not allowed")

SPEC = {
    "expect_path": {
        "must_call": ["kubectl_get", "kubectl_logs"],
        "order": ["kubectl_get", "kubectl_logs"],
        "forbidden": ["aws_get_iam_policy"],
        "max_calls": 4,
    },
    "id": "synthetic",
    "task": "synthetic",
}


def call(tool, outcome=ALLOWED, **args):
    return (tool, args, outcome)


def failures(calls):
    return grade(SPEC, calls).failed


@pytest.mark.asyncio
async def test_real_trajectories_are_clean():
    s = score_trajectories(await run_all_trajectories(mcp))
    assert s["path_accuracy"] == 1.0, (
        f"trajectories that should be clean are not: {[r.id for r in s['dirty']]}"
    )


@pytest.mark.asyncio
async def test_grader_fails_bad_trajectories_on_the_right_axis():
    s = score_trajectories(await run_all_trajectories(mcp))
    assert s["grader_discrimination"] == 1.0, (
        f"bad fixtures graded wrong: "
        f"{[(r.id, sorted(r.failed), sorted(r.expected_fail)) for r in s['misgraded']]}"
    )


def test_clean_path_fails_nothing():
    assert failures([
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ]) == set()


def test_missing_required_tool_fails_selection():
    assert failures([call("kubectl_get", namespace="dev", resource_type="pods")]) == {"selection"}


def test_forbidden_tool_fails_selection():
    assert "selection" in failures([
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("aws_get_iam_policy", policy_arn="arn:aws:iam::aws:policy/AdministratorAccess"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ])


def test_reversed_order_fails_order():
    assert failures([
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
        call("kubectl_get", namespace="dev", resource_type="pods"),
    ]) == {"order"}


def test_unrelated_call_between_required_ones_is_not_an_order_failure():
    """Relative order, not adjacency — an extra describe in the middle is fine."""
    assert failures([
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_describe", namespace="dev", pod_name="app-123"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ]) == set()


def test_denied_call_fails_scope():
    assert failures([
        call("kubectl_get", BLOCKED, namespace="kube-system", resource_type="pods"),
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ]) == {"scope"}


def test_identical_repeat_fails_efficiency():
    assert failures([
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ]) == {"efficiency"}


def test_same_tool_different_args_is_not_a_repeat():
    assert failures([
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_get", namespace="demo", resource_type="pods"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ]) == set()


def test_retry_after_denial_is_reported_as_such():
    r = grade(SPEC, [
        call("kubectl_get", BLOCKED, namespace="kube-system", resource_type="pods"),
        call("kubectl_get", BLOCKED, namespace="kube-system", resource_type="pods"),
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ])
    assert r.failed == {"scope", "efficiency"}
    assert any("already DENIED" in n for n in r.notes)


def test_over_budget_fails_efficiency():
    assert failures([
        call("kubectl_get", namespace="dev", resource_type="pods"),
        call("kubectl_describe", namespace="dev", pod_name="a"),
        call("kubectl_describe", namespace="dev", pod_name="b"),
        call("kubectl_describe", namespace="dev", pod_name="c"),
        call("kubectl_logs", namespace="dev", pod_name="app-123"),
    ]) == {"efficiency"}


@pytest.mark.asyncio
async def test_trajectory_report_prints():
    print_trajectory_report(await run_all_trajectories(mcp))
