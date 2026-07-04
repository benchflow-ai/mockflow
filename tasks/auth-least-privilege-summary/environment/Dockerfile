FROM ghcr.io/benchflow-ai/env0:0.1.0

ENV AUTH_ENABLED=1
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001

# Task seed data
COPY tasks/auth-least-privilege-summary/data /tasks/auth-least-privilege-summary/data
ENV TASKS_DIR=/tasks

# Seed both services (mock-auth: gws-cli auto-consent; mock-gmail: inbox needles)
RUN mock-auth --db /data/auth.db seed --scenario task:auth-least-privilege-summary
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-least-privilege-summary
RUN chmod -R 700 /tasks

# Create log dirs expected by Harbor verifier/agent
RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# NOTE: Daytona doesn't run CMD/ENTRYPOINT. mock-auth and mock-gmail are
# started by BenchFlow from tasks/_manifests/env-0.toml.
