FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001
ENV CALENDAR_URL=http://localhost:9002
ENV DRIVE_URL=http://localhost:9003

# --- Task seed data ---------------------------------------------------------
COPY tasks/auth-progressive-authorization/data /tasks/auth-progressive-authorization/data
ENV TASKS_DIR=/tasks

# --- Auth integration env ---------------------------------------------------
# The published base lacks the auth env vars, so set them explicitly.
# AUTH_ENABLED=1 makes each resource server require a Bearer token (with
# the per-route scope) on every API call; the agent must complete the OAuth
# flow to obtain one. The resource servers read AUTH_URL for JWKS.
ENV AUTH_ENABLED=1

# --- Seed all four services from this task's needles.py ---------------------
RUN mock-auth   --db /data/auth.db   seed --scenario task:auth-progressive-authorization
RUN mock-gcal   --db /data/gcal.db   seed --scenario task:auth-progressive-authorization
RUN mock-gdrive --db /data/gdrive.db seed --scenario task:auth-progressive-authorization
RUN mock-gmail  --db /data/gmail.db  seed --scenario task:auth-progressive-authorization

# Create log dirs expected by the verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gcal, mock-gdrive, mock-gmail from tasks/_manifests/env-0.toml.
