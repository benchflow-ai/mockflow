FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001

# --- Task seed data ---------------------------------------------------------
COPY tasks/auth-app-install-scope-eval/data /tasks/auth-app-install-scope-eval/data
ENV TASKS_DIR=/tasks

# --- Auth integration env ---------------------------------------------------
# The published base lacks the auth env vars, so set them explicitly.
# AUTH_ENABLED=1 makes the gmail server require a Bearer token on every
# /gmail/v1 call; the agent must complete the OAuth flow to obtain one.
ENV AUTH_ENABLED=1

# --- Seed both services from this task's needles.py -------------------------
RUN mock-auth --db /data/auth.db seed --scenario task:auth-app-install-scope-eval
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-app-install-scope-eval

# Create log dirs expected by the verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gmail from tasks/_manifests/env-0.toml.
