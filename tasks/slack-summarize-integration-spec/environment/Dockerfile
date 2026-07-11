FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV SLACK_URL=http://localhost:9005

# Remove config so agent cannot discover the DB path
RUN rm -f /etc/env0/config.toml /etc/env0/env.sh

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/slack-summarize-integration-spec/data /tasks/slack-summarize-integration-spec/data
ENV TASKS_DIR=/tasks

# Seed the task-specific scenario
RUN mock-slack --db /data/slack.db seed --scenario task:slack-summarize-integration-spec

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-slack from tasks/_manifests/env-0.toml.
