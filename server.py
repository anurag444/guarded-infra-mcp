import asyncio
import logging
from enum import Enum
from functools import lru_cache

from fastmcp import FastMCP
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from policy_middleware import PolicyMiddleware
import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("guarded-infra-mcp")

REQUEST_TIMEOUT_SECONDS = 10
session = boto3.Session(profile_name="guarded-ro")


class ResourceType(str, Enum):
    PODS = "pods"


@lru_cache(maxsize=1)
def load_k8s_client() -> client.CoreV1Api:
    config.load_kube_config()
    return client.CoreV1Api()


# Order matters: create the server, THEN attach the gate to it.
mcp = FastMCP("guarded-infra-mcp")
mcp.add_middleware(PolicyMiddleware())


@mcp.tool()
async def kubectl_get(namespace: str, resource_type: ResourceType) -> dict:
    """Read-only: list pods in a Kubernetes namespace."""
    if resource_type != ResourceType.PODS:
        return {"error": f"unsupported resource_type: {resource_type}"}

    try:
        v1 = load_k8s_client()
    except ConfigException as e:
        logger.error("Could not load kubeconfig: %s", e)
        return {"error": "kubernetes client is not configured (kubeconfig not found or invalid)"}

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(v1.list_namespaced_pod, namespace=namespace),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {"error": f"request timed out after {REQUEST_TIMEOUT_SECONDS}s"}
    except ApiException as e:
        if e.status == 404:
            return {"error": f"namespace '{namespace}' not found"}
        return {"error": f"kubernetes API error (status {e.status})"}

    pods = [
        {"name": p.metadata.name, "status": p.status.phase, "namespace": p.metadata.namespace}
        for p in result.items
    ]
    return {"pods": pods}


@mcp.tool()
async def kubectl_logs(namespace: str, pod_name: str) -> dict:
    """Read-only: fetch recent logs from a pod."""
    try:
        v1 = load_k8s_client()
    except ConfigException as e:
        logger.error("Could not load kubeconfig: %s", e)
        return {"error": "kubernetes client is not configured (kubeconfig not found or invalid)"}

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                v1.read_namespaced_pod_log,
                name=pod_name,
                namespace=namespace,
                tail_lines=200,
            ),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {"error": f"request timed out after {REQUEST_TIMEOUT_SECONDS}s"}
    except ApiException as e:
        if e.status == 404:
            return {"error": f"pod '{pod_name}' not found in namespace '{namespace}'"}
        return {"error": f"kubernetes API error (status {e.status})"}

    return {"logs": result}


@mcp.tool()
async def kubectl_describe(namespace: str, pod_name: str) -> dict:
    """Read-only: get detailed status and recent events for a pod."""
    try:
        v1 = load_k8s_client()
    except ConfigException as e:
        logger.error("Could not load kubeconfig: %s", e)
        return {"error": "kubernetes client is not configured (kubeconfig not found or invalid)"}

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(v1.read_namespaced_pod, name=pod_name, namespace=namespace),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {"error": f"request timed out after {REQUEST_TIMEOUT_SECONDS}s"}
    except ApiException as e:
        if e.status == 404:
            return {"error": f"pod '{pod_name}' not found in namespace '{namespace}'"}
        return {"error": f"kubernetes API error (status {e.status})"}

    return {
        "name": result.metadata.name,
        "status": result.status.phase,
        "node": result.spec.node_name,
        "containers": [c.name for c in result.spec.containers],
        "start_time": str(result.status.start_time),
    }

@mcp.tool()
async def aws_describe_instances(region: str) -> dict:
    """Read-only: list EC2 instances in a region."""
    ec2 = session.client("ec2", region_name=region)
    result = await asyncio.to_thread(ec2.describe_instances)
    return {"reservations": len(result.get("Reservations", []))}

@mcp.tool()
async def aws_get_iam_policy(policy_arn: str) -> dict:
    """Read-only: fetch metadata for an IAM policy."""
    iam = session.client("iam")
    result = await asyncio.to_thread(iam.get_policy, PolicyArn=policy_arn)
    return {"policy": result["Policy"]["PolicyName"]}

if __name__ == "__main__":
    mcp.run()