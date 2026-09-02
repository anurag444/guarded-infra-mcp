"""Asserts the harness's headline numbers, so a regression fails CI.

These are the two assertions that matter:
  block_rate == 1.0  — every attack that should be refused, is
  fpr == 0.0         — no legitimate request is wrongly refused

Needs no cluster and no AWS credentials: a call that passes the gate and
then fails downstream still counts as `allowed`, which is exactly what's
being measured.
"""

import pytest

from evals.report import print_report, score
from evals.runner import run_all
from server import mcp


@pytest.fixture(scope="module")
async def results():
    return await run_all(mcp)


@pytest.mark.asyncio
async def test_block_rate_is_total():
    s = score(await run_all(mcp))
    assert s["block_rate"] == 1.0, (
        f"attacks got through: {[r.id for r in s['missed_attacks']]}"
    )


@pytest.mark.asyncio
async def test_no_false_positives():
    s = score(await run_all(mcp))
    assert s["false_positive_rate"] == 0.0, (
        f"legitimate requests wrongly refused: {[r.id for r in s['false_positives']]}"
    )


@pytest.mark.asyncio
async def test_known_gaps_still_behave_as_documented():
    """If a gap case flips, someone either fixed it (update expect:) or
    something regressed. Either way it should surface, not pass silently."""
    s = score(await run_all(mcp))
    changed = [r.id for r in s["known_gaps"] if not r.correct]
    assert not changed, f"known-gap cases changed behaviour: {changed}"


@pytest.mark.asyncio
async def test_report_prints():
    print_report(await run_all(mcp))