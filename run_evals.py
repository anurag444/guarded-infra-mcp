"""CLI entry point for the eval harness.

Usage:  .venv/bin/python run_evals.py

Prints block rate, false-positive rate, per-category breakdown, and any
missed attacks / false positives / changed known-gaps. Needs no cluster
and no AWS credentials.
"""

import asyncio

from evals.report import print_report
from evals.runner import run_all
from server import mcp

if __name__ == "__main__":
    print_report(asyncio.run(run_all(mcp)))