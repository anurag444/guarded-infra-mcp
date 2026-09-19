#!/usr/bin/env bash
# Drives the demo recording. Regenerate the GIF with docs/record.sh.
#
# Every command below is real — the DENIED lines come from the policy engine,
# and the eval numbers are whatever the suites print on the day it was recorded.
set -u
cd "$(dirname "$0")/.."

PY=.venv/bin/python
say()  { printf '\033[36m%s\033[0m\n' "$1"; sleep 1.2; }
run()  { printf '\033[1;32m$\033[0m %s\n' "$1"; sleep 0.5; eval "$1"; sleep "${2:-3}"; }

clear
say "# guarded-infra-mcp — an MCP server an agent cannot talk its way past"
sleep 0.6

say "# one YAML file says what the agent may touch"
run "sed -n '12,30p' policy.yaml" 4

clear
# Rotate rather than delete: the trace query below should show this demo's
# own four calls, not an accumulated history, but the old trail is still kept.
[ -f audit.jsonl ] && mv audit.jsonl audit.prev.jsonl

say "# four real MCP calls, straight through the gate"
run "$PY demo.py 2>/dev/null" 7

clear
say "# every decision is audited — allowed or denied"
run "grep out_of_scope audit.jsonl | tail -1 | jq '{tool, namespace, decision, deny_category, reason}'" 5

say "# trace_id + seq rebuild the exact path the agent took"
run "./audit_queries.sh trace | head -8 | cut -c1-100" 4

clear
say "# and both are scored: the calls, and the path"
run "$PY run_evals.py 2>/dev/null | grep -E 'rate|accuracy|discrimination'" 7

clear
say "# 51 tests. 45 of them need no cluster and no AWS credentials."
sleep 2.5
