FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV GMAIL_URL=http://localhost:9001
ENV DRIVE_URL=http://localhost:9003
ENV DOCS_URL=http://localhost:9004

COPY tasks/multi-unapproved-clause-deploy/data /tasks/multi-unapproved-clause-deploy/data
ENV TASKS_DIR=/tasks

RUN mock-gdrive --db /data/gdrive.db seed --scenario task:multi-unapproved-clause-deploy
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db
RUN mock-gmail --db /data/gmail.db seed --scenario task:multi-unapproved-clause-deploy

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gdrive, mock-gdoc, mock-gmail from tasks/_manifests/env-0.toml.
