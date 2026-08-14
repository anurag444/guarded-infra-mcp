# Guarded Infra MCP

## What this is

## Policy Setup v1
Which tools can run at all? (kubectl_get, kubectl_logs, kubectl_describe)
Which namespaces can they touch? (dev, demo — a namespace in Kubernetes is a folder that isolates a group of resources; kube-system is where the cluster's own critical pieces live, so it's off-limits)
Which resource kinds? (pods, deployments, services — deliberately not secrets)
Which verbs? (get, list, logs — all read-only; no delete, no create)


## Why


## Architecture


## Design Decisions

## Setup


## Status

