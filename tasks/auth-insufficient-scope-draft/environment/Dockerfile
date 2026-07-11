FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001

# Task seed data
COPY tasks/auth-insufficient-scope-draft/data /tasks/auth-insufficient-scope-draft/data
ENV TASKS_DIR=/tasks

# The published base image predates auth: set the auth env explicitly.
# (gmail picks up AUTH_ENABLED=1 at server start and enforces OAuth.)
ENV AUTH_ENABLED=1

# Seed both services at build time
RUN mock-auth --db /data/auth.db seed --scenario task:auth-insufficient-scope-draft
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-insufficient-scope-draft

# Create log dirs expected by BenchFlow verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gmail from tasks/_manifests/env-0.toml.
