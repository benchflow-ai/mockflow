FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV CALENDAR_URL=http://localhost:9002

COPY tasks/gcal-ietf-interim-cancelled-sessions/data /tasks/gcal-ietf-interim-cancelled-sessions/data
ENV TASKS_DIR=/tasks

RUN mock-gcal --db /data/gcal.db seed --scenario task:gcal-ietf-interim-cancelled-sessions

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-gcal from tasks/_manifests/env-0.toml.
