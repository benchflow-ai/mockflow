FROM ghcr.io/benchflow-ai/env0:0.1.0

# Task seed data (shared needles.py dispatches to per-env modules)
COPY tasks/multi-mail-cal-sync/data /tasks/multi-mail-cal-sync/data
ENV TASKS_DIR=/tasks

# Seed mock-gmail (emails with meeting arrangements)
RUN mock-gmail --db /data/gmail.db seed --scenario task:multi-mail-cal-sync

# Seed mock-gcal (hectic week + planted events)
RUN mock-gcal --db /data/gcal.db seed --scenario task:multi-mail-cal-sync

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts
