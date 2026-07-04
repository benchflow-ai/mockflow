FROM ghcr.io/benchflow-ai/env0:0.1.0

WORKDIR /app
ENV TASK_ROOT=/var/lib/task

COPY example_tasks/gdrive-archive-stale-drafts/data /var/lib/task/data
COPY example_tasks/gdrive-archive-stale-drafts/oracle /var/lib/task/oracle

RUN chmod 700 /var/lib/task && \
    mock-gdrive --db /data/gdrive.db seed \
      --task-data /var/lib/task/data \
      --task-name gdrive-archive-stale-drafts

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
