FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV CALENDAR_URL=http://localhost:9002
ENV SLACK_URL=http://localhost:9005

COPY tasks/multi-weekend-deploy-coverage/data /tasks/multi-weekend-deploy-coverage/data
ENV TASKS_DIR=/tasks

RUN mock-slack --db /data/slack.db seed --scenario task:multi-weekend-deploy-coverage
RUN mock-gcal --db /data/gcal.db seed --scenario task:multi-weekend-deploy-coverage

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-slack, mock-gcal from tasks/_manifests/env-0.toml.
