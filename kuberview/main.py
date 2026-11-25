"""KuberView — a tiny Kubernetes dashboard built for learning.

Talks to the cluster using the official `kubernetes` Python client and the
kubeconfig on this machine (same credentials kubectl uses).
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from kubernetes import client, config

config.load_kube_config()

core = client.CoreV1Api()
apps = client.AppsV1Api()
batch = client.BatchV1Api()

app = FastAPI(title="KuberView")

STATIC_DIR = Path(__file__).parent / "static"


def age(ts) -> str:
    """Human-friendly age like kubectl's AGE column."""
    if ts is None:
        return ""
    delta = datetime.now(timezone.utc) - ts
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h{(secs % 3600) // 60}m"
    return f"{secs // 86400}d"


@app.get("/api/overview")
def overview():
    pods = core.list_pod_for_all_namespaces().items
    phases: dict[str, int] = {}
    for p in pods:
        phases[p.status.phase] = phases.get(p.status.phase, 0) + 1
    return {
        "nodes": len(core.list_node().items),
        "namespaces": len(core.list_namespace().items),
        "pods": len(pods),
        "podPhases": phases,
        "deployments": len(apps.list_deployment_for_all_namespaces().items),
        "services": len(core.list_service_for_all_namespaces().items),
    }


@app.get("/api/namespaces")
def namespaces():
    return [
        {"name": ns.metadata.name, "status": ns.status.phase, "age": age(ns.metadata.creation_timestamp)}
        for ns in core.list_namespace().items
    ]


@app.get("/api/nodes")
def nodes():
    out = []
    for n in core.list_node().items:
        conditions = {c.type: c.status for c in (n.status.conditions or [])}
        out.append(
            {
                "name": n.metadata.name,
                "ready": conditions.get("Ready", "Unknown"),
                "roles": [
                    k.rsplit("/", 1)[1]
                    for k in n.metadata.labels
                    if k.startswith("node-role.kubernetes.io/")
                ],
                "version": n.status.node_info.kubelet_version,
                "os": n.status.node_info.os_image,
                "cpu": n.status.capacity.get("cpu"),
                "memory": n.status.capacity.get("memory"),
                "age": age(n.metadata.creation_timestamp),
            }
        )
    return out


@app.get("/api/pods")
def pods(namespace: str = Query(default="")):
    items = (
        core.list_namespaced_pod(namespace).items
        if namespace
        else core.list_pod_for_all_namespaces().items
    )
    out = []
    for p in items:
        statuses = p.status.container_statuses or []
        ready = sum(1 for c in statuses if c.ready)
        restarts = sum(c.restart_count for c in statuses)
        out.append(
            {
                "name": p.metadata.name,
                "namespace": p.metadata.namespace,
                "phase": p.status.phase,
                "ready": f"{ready}/{len(p.spec.containers)}",
                "restarts": restarts,
                "node": p.spec.node_name,
                "ip": p.status.pod_ip,
                "containers": [c.name for c in p.spec.containers],
                "age": age(p.metadata.creation_timestamp),
            }
        )
    return out


@app.get("/api/deployments")
def deployments(namespace: str = Query(default="")):
    items = (
        apps.list_namespaced_deployment(namespace).items
        if namespace
        else apps.list_deployment_for_all_namespaces().items
    )
    return [
        {
            "name": d.metadata.name,
            "namespace": d.metadata.namespace,
            "ready": f"{d.status.ready_replicas or 0}/{d.spec.replicas}",
            "upToDate": d.status.updated_replicas or 0,
            "available": d.status.available_replicas or 0,
            "images": [c.image for c in d.spec.template.spec.containers],
            "age": age(d.metadata.creation_timestamp),
        }
        for d in items
    ]


@app.get("/api/services")
def services(namespace: str = Query(default="")):
    items = (
        core.list_namespaced_service(namespace).items
        if namespace
        else core.list_service_for_all_namespaces().items
    )
    return [
        {
            "name": s.metadata.name,
            "namespace": s.metadata.namespace,
            "type": s.spec.type,
            "clusterIP": s.spec.cluster_ip,
            "ports": [f"{p.port}/{p.protocol}" for p in (s.spec.ports or [])],
            "age": age(s.metadata.creation_timestamp),
        }
        for s in items
    ]


@app.get("/api/events")
def events(namespace: str = Query(default="")):
    items = (
        core.list_namespaced_event(namespace).items
        if namespace
        else core.list_event_for_all_namespaces().items
    )
    items.sort(key=lambda e: e.last_timestamp or e.metadata.creation_timestamp, reverse=True)
    return [
        {
            "type": e.type,
            "reason": e.reason,
            "object": f"{e.involved_object.kind}/{e.involved_object.name}",
            "namespace": e.metadata.namespace,
            "message": e.message,
            "age": age(e.last_timestamp or e.metadata.creation_timestamp),
        }
        for e in items[:50]
    ]


@app.get("/api/pods/{namespace}/{name}/logs")
def pod_logs(namespace: str, name: str, container: str = Query(default=""), tail: int = 100):
    try:
        return {
            "logs": core.read_namespaced_pod_log(
                name,
                namespace,
                container=container or None,
                tail_lines=tail,
            )
        }
    except client.ApiException as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
