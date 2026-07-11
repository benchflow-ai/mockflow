FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV CALENDAR_URL=http://localhost:9002

# --- Task seed data ---------------------------------------------------------
COPY tasks/auth-service-account-impersonation/data /tasks/auth-service-account-impersonation/data
ENV TASKS_DIR=/tasks

# --- Auth integration env ---------------------------------------------------
# The published base lacks the auth env vars, so set them explicitly.
# AUTH_ENABLED=1 makes the gcal server require a Bearer token on every
# /calendar/v3 call; the agent must mint a service-account token to create the
# event. CALENDAR_URL is gcal's own env var (see config.toml).
ENV AUTH_ENABLED=1

# --- Seed both services from this task's needles.py -------------------------
RUN mock-auth --db /data/auth.db seed --scenario task:auth-service-account-impersonation
RUN mock-gcal --db /data/gcal.db seed --scenario task:auth-service-account-impersonation

# Create log dirs expected by the verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gcal from tasks/_manifests/env-0.toml.
