FROM ghcr.io/benchflow-ai/env0:0.1.0

COPY tasks/gcal-federal-register-meeting-amendments/data /tasks/gcal-federal-register-meeting-amendments/data
ENV TASKS_DIR=/tasks

RUN mock-gcal --db /data/gcal.db seed --scenario task:gcal-federal-register-meeting-amendments

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

RUN chown agent:agent /logs/agent /logs/artifacts
