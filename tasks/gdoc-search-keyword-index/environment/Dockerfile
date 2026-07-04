FROM ghcr.io/benchflow-ai/env0:0.1.0

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/gdoc-search-keyword-index/data /tasks/gdoc-search-keyword-index/data
ENV TASKS_DIR=/tasks

# mock-gdrive seeds first (metadata + content authority, includes filler)
RUN mock-gdrive --db /data/gdrive.db seed --scenario task:gdoc-search-keyword-index
# mock-gdoc mirrors mock-gdrive (derives body_json from content_text)
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts
