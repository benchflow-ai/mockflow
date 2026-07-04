FROM ghcr.io/benchflow-ai/env-0-base:latest

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/gdoc-search-keyword-index/data /tasks/gdoc-search-keyword-index/data
ENV TASKS_DIR=/tasks

# gdrive seeds first (metadata + content authority, includes filler)
RUN gdrive --db /data/gdrive.db seed --scenario task:gdoc-search-keyword-index
# gdoc mirrors gdrive (derives body_json from content_text)
RUN gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env-0-base)
RUN chown agent:agent /logs/agent /logs/artifacts
