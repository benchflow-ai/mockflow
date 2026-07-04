FROM ghcr.io/benchflow-ai/env0:0.1.0

COPY tasks/gdrive-sensitive-file-lockdown/data /tasks/gdrive-sensitive-file-lockdown/data
ENV TASKS_DIR=/tasks

RUN mock-gdrive --db /data/gdrive.db seed --scenario task:gdrive-sensitive-file-lockdown

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts
