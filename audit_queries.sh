#!/usr/bin/env bash
# jq queries over audit.jsonl — the observability layer, no daemon required.
#
# Every line of audit.jsonl is a standalone JSON object, which is the whole
# reason these are one-liners. The same field names would map to Splunk
# (index=guarded_infra deny_category=*), Loki, or DuckDB's read_json_auto if
# this ever needs a hosted index; nothing below is tied to jq.
#
# Usage:  ./audit_queries.sh          run every query
#         ./audit_queries.sh denials  run one, by name
set -euo pipefail

LOG="$(dirname "$0")/audit.jsonl"
[ -f "$LOG" ] || { echo "no $LOG yet — run the server or: .venv/bin/python run_evals.py"; exit 1; }

hdr() { printf '\n\033[1m── %s\033[0m\n   %s\n' "$1" "$2"; }

# Everything the gate refused, newest last. The first question after any
# incident: what did the agent try that it was not allowed to do?
denials() {
  hdr "denials" "every refused call, with its reason"
  jq -r 'select(.decision=="deny")
         | "\(.ts)  \(.tool)  \(.deny_category)  \(.reason)"' "$LOG"
}

# Deny rate is the health metric. Near 0% means the policy matches how the
# agent actually works; a spike means either an attack or a policy that has
# drifted out of step with a legitimate workflow — both worth a look.
rate() {
  hdr "decision rate" "allow vs deny, overall"
  jq -s 'group_by(.decision)
         | map({decision: .[0].decision, count: length})
         | . as $g
         | ($g | map(.count) | add) as $total
         | $g | map(. + {pct: (100 * .count / $total | round)})' "$LOG"
}

# Which class of denial dominates. out_of_scope_namespace is routine probing;
# a run of unlisted_tool means the agent believes in tools that do not exist,
# which is a prompt/tool-description problem, not a policy one.
categories() {
  hdr "deny categories" "which kind of refusal, ranked"
  jq -s 'map(select(.decision=="deny").deny_category)
         | group_by(.) | map({category: .[0], count: length})
         | sort_by(-.count)' "$LOG"
}

# Per-tool volume and denial count — shows which tool the agent leans on and
# which one it keeps getting refused for.
tools() {
  hdr "tool usage" "calls and denials per tool"
  jq -s 'group_by(.tool)
         | map({tool: .[0].tool,
                calls: length,
                denied: (map(select(.decision=="deny")) | length)})
         | sort_by(-.calls)' "$LOG"
}

# The trajectory view: one agent run, in order. This is the audit file paying
# off — trace_id + seq reconstruct the exact path the agent took, which is the
# same thing evals/trajectory.py grades.
trace() {
  hdr "traces" "each session's call path, in order"
  jq -s 'group_by(.trace_id)
         | map({trace: .[0].trace_id,
                calls: length,
                path: (sort_by(.seq) | map("\(.tool)[\(.decision)]") | join(" -> "))})
         | sort_by(-.calls) | .[:10]' "$LOG"
}

# Sessions that got refused more than once. A single denial is an agent
# learning a boundary; repeated denials in one trace is an agent hammering it.
repeat_offenders() {
  hdr "repeat offenders" "sessions with more than one denial"
  jq -s 'map(select(.decision=="deny"))
         | group_by(.trace_id)
         | map({trace: .[0].trace_id, denials: length,
                categories: (map(.deny_category) | unique)})
         | map(select(.denials > 1)) | sort_by(-.denials)' "$LOG"
}

# Latency of calls that actually ran. Denials are excluded: they short-circuit
# before the tool body, so counting their (null) time would flatter the number.
latency() {
  hdr "latency" "p50/p95/max over calls that ran"
  jq -s 'map(select(.latency_ms != null) | .latency_ms) | sort
         | if length == 0 then "no completed calls yet"
           else {n: length,
                 p50: .[(length * 0.5 | floor)],
                 p95: .[(length * 0.95 | floor)],
                 max: .[-1]}
           end' "$LOG"
}

# Calls the gate allowed that then failed downstream. Separating these from
# denials matters: "we refused it" and "we permitted it and the cluster was
# down" are different problems with different owners.
backend_errors() {
  hdr "backend errors" "allowed by policy, failed in the backend"
  jq -s 'map(select(.outcome=="error"))
         | group_by(.tool) | map({tool: .[0].tool, errors: length})' "$LOG"
}

ALL=(rate categories tools denials trace repeat_offenders latency backend_errors)

if [ $# -gt 0 ]; then "$1"; else for q in "${ALL[@]}"; do "$q"; done; fi
