FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV DRIVE_URL=http://localhost:9003

COPY tasks/gdrive-archive-stale-drafts/data /tasks/gdrive-archive-stale-drafts/data
ENV TASKS_DIR=/tasks

RUN mock-gdrive --db /data/gdrive.db seed --scenario task:gdrive-archive-stale-drafts

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gdrive from tasks/_manifests/env-0.toml.
