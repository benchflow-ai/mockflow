FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV SLACK_URL=http://localhost:9005

# Seed data
COPY tasks/slack-do-not-kick-innocent/data /tasks/slack-do-not-kick-innocent/data
ENV TASKS_DIR=/tasks

RUN mock-slack --db /data/slack.db seed --scenario task:slack-do-not-kick-innocent

# Create log dirs expected by BenchFlow verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-slack from tasks/_manifests/env-0.toml.
