# ==============================================================================
# Production Dockerfile: Autonomous AI Multi-Agent Coding Engine
# Multi-stage secure build, non-root user execution, and container health checking.
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Final Production Image
FROM python:3.11-slim AS runner

WORKDIR /app

# Install minimal runtime tools: git (for repo operations), curl (for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create unprivileged application user
RUN groupadd -g 1001 agentgroup && \
    useradd -u 1001 -g agentgroup -m -d /home/agentuser -s /bin/sh agentuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/agentuser/.local

# Copy application source code
COPY --chown=agentuser:agentgroup agent/ ./agent/
COPY --chown=agentuser:agentgroup web/ ./web/
COPY --chown=agentuser:agentgroup server.py main.py pytest.ini pyproject.toml ./

# Create directories for persistent checkpoints and isolated workspaces
RUN mkdir -p /app/.checkpoints /app/workspaces && \
    chown -R agentuser:agentgroup /app /home/agentuser

# Security: drop privileges
USER 1001:1001

ENV PATH="/home/agentuser/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    ALLOW_UNSAFE_HOST_FALLBACK=1

EXPOSE 8000

# Container Orchestrator Health Check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

