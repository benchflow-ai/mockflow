FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV CALENDAR_URL=http://localhost:9002
ENV DRIVE_URL=http://localhost:9003
ENV DOCS_URL=http://localhost:9004
ENV SLACK_URL=http://localhost:9005

COPY tasks/multi-rebalance-on-call-rotation/data /tasks/multi-rebalance-on-call-rotation/data
ENV TASKS_DIR=/tasks

# gdrive seeds first (metadata + content authority, includes filler)
RUN mock-gdrive --db /data/gdrive.db seed --scenario task:multi-rebalance-on-call-rotation
# gdoc mirrors gdrive (derives body_json from content_text)
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db
RUN mock-gcal --db /data/gcal.db seed --scenario task:multi-rebalance-on-call-rotation
RUN mock-slack --db /data/slack.db seed --scenario task:multi-rebalance-on-call-rotation

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gdrive, mock-gdoc, mock-gcal, mock-slack from tasks/_manifests/env-0.toml.
