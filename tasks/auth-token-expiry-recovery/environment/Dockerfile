FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001

# Auth wiring. The published base image predates auth, so set its env vars
# here. AUTH_ENABLED=1 turns on Bearer-JWT enforcement in gmail.
ENV AUTH_ENABLED=1

# Seed data
COPY tasks/auth-token-expiry-recovery/data /tasks/auth-token-expiry-recovery/data
ENV TASKS_DIR=/tasks

RUN mock-auth --db /data/auth.db seed --scenario task:auth-token-expiry-recovery
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-token-expiry-recovery

# Create log dirs expected by BenchFlow verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gmail from tasks/_manifests/env-0.toml.
