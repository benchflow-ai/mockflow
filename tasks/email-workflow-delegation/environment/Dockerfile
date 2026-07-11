FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV GMAIL_URL=http://localhost:9001

# Seed data
COPY tasks/email-workflow-delegation/data /tasks/email-workflow-delegation/data
ENV TASKS_DIR=/tasks

RUN mock-gmail --db /data/gmail.db seed --scenario task:email-workflow-delegation

# Create log dirs expected by BenchFlow verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gmail from tasks/_manifests/env-0.toml.
