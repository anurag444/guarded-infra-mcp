# guarded-infra-mcp

An MCP server that gives an AI agent read-only access to a Kubernetes cluster
and an AWS account — through a policy gate that refuses anything not explicitly
allowed, audits every decision, and is scored by two eval suites.

## What this is

Five tools (`kubectl_get`, `kubectl_logs`, `kubectl_describe`,
`aws_describe_instances`, `aws_get_iam_policy`) exposed over MCP. Every call —
no exceptions — passes through one middleware that checks it against
`policy.yaml` before the tool body runs, and writes the decision to
`audit.jsonl` whether it was allowed or denied.

Two questions are measured separately, because they fail for different reasons:

| suite | question | headline |
|---|---|---|
| `evals/cases/{attacks,legit}.yaml` | should **this call** be allowed? | block rate 100%, false-positive rate 0% |
| `evals/cases/trajectories.yaml` | was the **whole path** right? | path accuracy 100%, grader discrimination 100% |

## Why

An agent with cluster credentials is a credential-holder that improvises. The
usual answers are a system prompt ("please don't read secrets") or a read-only
service account. The first is a suggestion, not a control. The second is real
but coarse: it cannot say "pods in `dev` and `demo`, never `kube-system`", and
it leaves no record of what was attempted.

So the gate is code, not prose — deny-by-default, declared in one YAML file,
enforced in one middleware that no tool can bypass because no tool invokes it.
And because a gate that is never measured is a gate nobody trusts, both its
strictness and its permissiveness are scored in CI.

## Architecture

```mermaid
flowchart TB
    Agent["MCP host / agent<br/>(Claude Code, VS Code)"]

    subgraph Server["server.py — FastMCP"]
        MW["PolicyMiddleware.on_call_tool<br/><i>the single gate</i>"]
        Tools["tool bodies<br/>kubectl_get · kubectl_logs · kubectl_describe<br/>aws_describe_instances · aws_get_iam_policy"]
    end

    Policy[("policy.yaml<br/>deny-by-default allowlist")]
    Engine["policy.check()<br/><i>pure function, no I/O</i>"]
    Audit[("audit.jsonl<br/>every decision, allowed or denied")]

    K8s["Kubernetes API<br/>(k3d)"]
    AWS["AWS<br/>EC2 · IAM"]

    Agent -->|"call_tool"| MW
    MW -->|"tool + scope dims"| Engine
    Policy --> Engine
    Engine -->|"Decision(allowed, reason, category)"| MW
    MW -->|"every decision"| Audit
    MW -.->|"DENIED: reason<br/><b>tool body never runs</b>"| Agent
    MW -->|"allowed"| Tools
    Tools --> K8s
    Tools --> AWS

    Audit --> JQ["audit_queries.sh<br/>deny rate · categories · traces · latency"]
    Audit -.->|"trace_id + seq<br/>rebuild the path"| Traj

    subgraph Evals["eval suites — no cluster or AWS creds required"]
        Calls["call evals<br/>block rate · false-positive rate"]
        Traj["trajectory evals<br/>selection · order · scope · efficiency"]
    end

    Calls -->|"replayed through the real gate"| MW
    Traj -->|"replayed through the real gate"| MW
```

The two dotted edges are the design in one picture: a denial short-circuits
before the tool body exists, and the audit trail feeds the trajectory grader.

## Policy

`policy.yaml` is the only place permissions are stated. Each tool declares
which dimensions to check and where each value comes from — an argument
(`from_arg`) or a constant the caller cannot influence (`fixed`):

```yaml
kubectl_logs:
  checks:
    namespace: {from_arg: namespace}
    resource:  {fixed: pods}      # caller cannot widen this
```

Current scope: namespaces `dev`, `demo` — resources `pods` (`secrets`
deliberately absent) — region `ca-central-1` — verbs read-only, since no
mutating tool exists to call.

The middleware knows nothing about what "namespace" or "region" mean. It reads
each tool's declared `checks`, pulls those values, and hands them to
`check()`. That is what makes "one gate, two backends" true in code rather than
just in this README: adding an AWS tool required no new gate logic, only a
`tools:` entry.

## Eval suites

```
.venv/bin/python run_evals.py                # both
.venv/bin/python run_evals.py --calls        # gate only
.venv/bin/python run_evals.py --trajectories # paths only
```

**Call evals** — 17 attack fixtures that must be refused, 10 legitimate ones
that must pass, plus 2 recorded known gaps. Block rate alone is meaningless: a
gate that denies everything scores 100%. Reporting false-positive rate beside
it is what shows the gate discriminates rather than just refuses.

```
block rate           100%   (17/17 attacks refused)
false positive rate  0%     (0/10 legit requests wrongly refused)
```

Attack categories: unlisted tool · out-of-scope namespace · forbidden resource ·
wrong region · string-mangling bypass · type confusion · missing arg ·
injection into ungated args.

**Trajectory evals** — the path, not the answer. Each fixture is a whole run,
replayed through the real gate and graded on four axes that are reported
separately, never averaged:

- **selection** — right tools called, no forbidden tool touched
- **order** — required tools in the declared relative order
- **scope** — no call refused by the gate (a blocked probe is still a probe)
- **efficiency** — no identical repeat, no retry after `DENIED`, within budget

```
path accuracy         100%   (4/4 real runs clean on all four axes)
grader discrimination 100%   (6/6 bad runs failed exactly the intended axis)
```

They stay separate because they get fixed in different places: selection and
order are prompt and tool-description problems, scope is a policy or grounding
problem, efficiency is loop control. One blended score tells you none of that.

The case that justifies the whole suite is `bad-wanders-into-aws`: an agent
debugging a pod that also reads `AdministratorAccess`. **Every call in it is
individually allowed.** The call evals score that trajectory perfect. Only a
path-level grader fails it.

`grader_discrimination` is the metric that protects the metric — each
deliberately-broken fixture must fail exactly the axis it breaks and no other,
so a grader that passes everything scores 0 instead of looking healthy.

## Audit trail

One JSON object per line, appended for every decision:

```json
{"ts":"2026-09-19T17:44:48Z","trace_id":"c27ff681…","seq":1,"request_id":"1",
 "tool":"kubectl_get","namespace":"kube-system","resource":"pods",
 "allowed":false,"decision":"deny","deny_category":"out_of_scope_namespace",
 "reason":"namespace 'kube-system' is not allowed; permitted namespaces are ['dev', 'demo']",
 "latency_ms":null,"outcome":"denied"}
```

`deny_category` is set by the policy engine, not regex'd back out of the
message, so the prose can be reworded without breaking any query.
`latency_ms` is null on a denial because nothing ran, and `outcome`
distinguishes "we refused it" from "we allowed it and the backend was down" —
different problems, different owners.

`trace_id` + `seq` group one agent session into one ordered path, which is what
makes the file readable as trajectories rather than a flat list:

```
./audit_queries.sh          # all queries
./audit_queries.sh trace    # kubectl_get[allow] -> kubectl_describe[allow] -> kubectl_get[deny] -> …
```

`audit_queries.sh` holds 8 jq queries — deny rate, deny categories, per-tool
usage, denials, traces, repeat offenders, latency p50/p95/max, backend errors.
jq because JSONL needs no daemon to be queryable; the same field names map
onto Splunk, Loki, or DuckDB's `read_json_auto` if this ever needs a hosted
index.

## Design decisions

**Gate as middleware, not as a decorator on each tool.** A decorator is opt-in,
and the tool someone adds at 6pm is the one that forgets it. `on_call_tool`
fires on every call including tools that do not exist, so an unregistered tool
name is denied before its arguments are read.

**The policy engine is a pure function.** `policy.check()` imports no MCP, no
kubernetes, no boto3. It takes a dict and returns a `Decision`, so the entire
allow/deny matrix is testable with plain pytest and no cluster.

**Denials return `ToolError`, not an empty result.** The agent receives the
reason and can stop; an empty list reads as "nothing there" and invites a
retry loop against a boundary that will never move.

**Evals classify "allowed" as "the gate let it through", not "it worked".** A
call that clears the gate and then fails on a dead cluster still counts as
allowed, because gate behaviour is the only thing under test. That is why both
suites run with no cluster and no AWS credentials.

**Known gaps are recorded as cases, not hidden.** `pod_name` and `policy_arn`
have no `checks` entry, so injection-shaped values in those arguments pass. Two
fixtures assert that gap as current behaviour: they fail loudly the day it
changes, in either direction.

## Setup

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

k3d cluster create guarded            # local Kubernetes
aws configure --profile guarded-ro    # read-only AWS profile

.venv/bin/python server.py            # run the server
.venv/bin/python -m pytest            # 51 tests
.venv/bin/python run_evals.py         # both eval suites
```

The eval suites and every test except `test_server.py` run with no cluster and
no AWS credentials.

Register with an MCP host (`.vscode/mcp.json` is already checked in):

```json
{"command": ".venv/bin/python", "args": ["server.py"]}
```

## Status

Working: five read-only tools across two backends, one policy gate, JSONL audit
trail with jq queries, 51 tests, and both eval suites at 100% / 0%.

Next: close the two recorded injection gaps by giving `pod_name` and
`policy_arn` their own `checks` entries; drive trajectory evals from a live
agent instead of scripted fixtures, reusing the same four-axis grader against
paths rebuilt from `audit.jsonl`.
