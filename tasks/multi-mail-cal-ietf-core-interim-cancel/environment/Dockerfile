FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV GMAIL_URL=http://localhost:9001
ENV CALENDAR_URL=http://localhost:9002

COPY tasks/multi-mail-cal-ietf-core-interim-cancel/data /tasks/multi-mail-cal-ietf-core-interim-cancel/data
ENV TASKS_DIR=/tasks

RUN mock-gmail --db /data/gmail.db seed --scenario task:multi-mail-cal-ietf-core-interim-cancel
RUN mock-gcal --db /data/gcal.db seed --scenario task:multi-mail-cal-ietf-core-interim-cancel

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gmail, mock-gcal from tasks/_manifests/env-0.toml.
