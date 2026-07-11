FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV DRIVE_URL=http://localhost:9003
ENV DOCS_URL=http://localhost:9004

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/gdoc-redact-confidential/data /tasks/gdoc-redact-confidential/data
ENV TASKS_DIR=/tasks

# gdrive seeds first (metadata + content authority, includes filler)
RUN mock-gdrive --db /data/gdrive.db seed --scenario task:gdoc-redact-confidential
# gdoc mirrors gdrive (derives body_json from content_text)
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gdrive, mock-gdoc from tasks/_manifests/env-0.toml.
