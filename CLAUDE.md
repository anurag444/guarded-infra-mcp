# guarded-infra-mcp

An MCP server exposing scoped, policy-gated access to a Kubernetes cluster and AWS account.

## Stack
Python 3.11, MCP Python SDK, k3d for local cluster, pytest for tests.

## Conventions
- Every tool has a typed JSON schema for input and output.
- Reads are unrestricted; writes require explicit human confirmation.
- No destructive kubectl/aws calls without going through the policy layer.

## Commands
- Run server: `python server.py`
- Run tests: `pytest`
