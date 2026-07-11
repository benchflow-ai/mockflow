FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV GMAIL_URL=http://localhost:9001
ENV DRIVE_URL=http://localhost:9003
ENV DOCS_URL=http://localhost:9004
ENV SLACK_URL=http://localhost:9005

COPY tasks/multi-misread-approval-scope/data /tasks/multi-misread-approval-scope/data
ENV TASKS_DIR=/tasks

RUN mock-slack --db /data/slack.db seed --scenario task:multi-misread-approval-scope
RUN mock-gmail --db /data/gmail.db seed --scenario task:multi-misread-approval-scope
RUN mock-gdrive --db /data/gdrive.db seed --scenario task:multi-misread-approval-scope
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-slack, mock-gmail, mock-gdrive, mock-gdoc from tasks/_manifests/env-0.toml.
