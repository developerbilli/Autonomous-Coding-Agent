"""Tests for Production Deployment, Health Monitoring, and Operational Readiness."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server import app

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_dockerfile_production_hardening_specifications():
    """Verify Dockerfile enforces multi-stage build, non-root user (UID 1001), and HEALTHCHECK."""
    dockerfile_path = ROOT_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Production Dockerfile must exist"

    content = dockerfile_path.read_text(encoding="utf-8")

    # Multi-stage build
    assert "AS builder" in content
    assert "AS runner" in content

    # Non-root unprivileged execution
    assert "USER 1001:1001" in content
    assert "groupadd -g 1001" in content
    assert "useradd -u 1001" in content

    # Container health checking
    assert "HEALTHCHECK" in content
    assert "http://localhost:8000/health" in content

    # Clean caching
    assert "--no-cache-dir" in content
    assert "rm -rf /var/lib/apt/lists/*" in content


def test_docker_compose_orchestration_specifications():
    """Verify docker-compose defines resource quotas, persistent volumes, and sandbox workers."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    content = compose_path.read_text(encoding="utf-8")

    # Services
    assert "agent-engine:" in content
    assert "sandbox-worker:" in content

    # Sandboxing constraints
    assert 'network_mode: "none"' in content
    assert "read_only: true" in content

    # Volumes
    assert "checkpoints_data:" in content
    assert "workspaces_data:" in content


def test_health_check_endpoint_operational_readiness():
    """Verify /health endpoint reports healthy components and operational status."""
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ("healthy", "degraded")
    assert data["service"] == "autonomous-ai-coding-agent"
    assert "uptime_seconds" in data
    assert "components" in data

    components = data["components"]
    assert "checkpointer" in components
    assert "long_term_memory" in components
    assert "sandbox" in components

    assert components["checkpointer"]["status"] == "healthy"
    assert components["long_term_memory"]["status"] == "healthy"


def test_prometheus_metrics_endpoint():
    """Verify /metrics returns standard Prometheus plain text metrics."""
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    text = response.text
    assert "coding_agent_up 1" in text
    assert "coding_agent_uptime_seconds" in text
    assert "coding_agent_memory_episodes_total" in text
    assert "coding_agent_semantic_patterns_total" in text

