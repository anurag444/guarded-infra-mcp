"""CLI entry point for the eval harnesses.

Usage:
    .venv/bin/python run_evals.py                # both suites
    .venv/bin/python run_evals.py --calls        # single-call gate evals only
    .venv/bin/python run_evals.py --trajectories # path evals only

Call evals print block rate + false-positive rate. Trajectory evals print
path accuracy + grader discrimination, broken out by axis. Neither needs a
cluster or AWS credentials.
"""

import asyncio
import sys

from evals.report import print_report, print_trajectory_report
from evals.runner import run_all
from evals.trajectory import run_all_trajectories
from server import mcp


async def main(calls: bool, trajectories: bool):
    if calls:
        print_report(await run_all(mcp))
    if trajectories:
        print_trajectory_report(await run_all_trajectories(mcp))


if __name__ == "__main__":
    only_calls = "--calls" in sys.argv
    only_traj = "--trajectories" in sys.argv
    both = not (only_calls or only_traj)
    asyncio.run(main(only_calls or both, only_traj or both))
