FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV DRIVE_URL=http://localhost:9003
ENV DOCS_URL=http://localhost:9004
ENV SLACK_URL=http://localhost:9005

COPY tasks/multi-doc-slack-spec-drift/data /tasks/multi-doc-slack-spec-drift/data
ENV TASKS_DIR=/tasks

RUN mock-gdrive --db /data/gdrive.db seed --scenario task:multi-doc-slack-spec-drift
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db
RUN mock-slack --db /data/slack.db seed --scenario task:multi-doc-slack-spec-drift

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gdrive, mock-gdoc, mock-slack from tasks/_manifests/env-0.toml.
