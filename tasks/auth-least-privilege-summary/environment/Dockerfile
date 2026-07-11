FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001

ENV AUTH_ENABLED=1

# Task seed data
COPY tasks/auth-least-privilege-summary/data /tasks/auth-least-privilege-summary/data
ENV TASKS_DIR=/tasks

# Seed both services (mock-auth: gws-cli auto-consent; mock-gmail: inbox needles)
RUN mock-auth --db /data/auth.db seed --scenario task:auth-least-privilege-summary
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-least-privilege-summary
RUN chmod -R 700 /tasks

# Create log dirs expected by BenchFlow verifier/agent
RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gmail from tasks/_manifests/env-0.toml.
