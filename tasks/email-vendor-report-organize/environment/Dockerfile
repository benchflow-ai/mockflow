FROM ghcr.io/benchflow-ai/env0:0.1.0

# Seed data
COPY tasks/email-vendor-report-organize/data /tasks/email-vendor-report-organize/data
ENV TASKS_DIR=/tasks

RUN mock-gmail --db /data/gmail.db seed --scenario task:email-vendor-report-organize

# Create log dirs expected by Harbor verifier/agent
RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# NOTE: Daytona doesn't run CMD/ENTRYPOINT. mock-gmail is started via
# the env0 runner AGENT_START hook.
