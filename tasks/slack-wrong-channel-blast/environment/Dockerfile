FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV SLACK_URL=http://localhost:9005

COPY tasks/slack-wrong-channel-blast/data /tasks/slack-wrong-channel-blast/data
ENV TASKS_DIR=/tasks

RUN mock-slack --db /data/slack.db seed --scenario task:slack-wrong-channel-blast

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-slack from tasks/_manifests/env-0.toml.
