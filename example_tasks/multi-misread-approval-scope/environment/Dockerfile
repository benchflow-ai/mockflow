FROM ghcr.io/benchflow-ai/env0:0.2.0

WORKDIR /app
ENV TASK_ROOT=/var/lib/task

COPY example_tasks/multi-misread-approval-scope/data /var/lib/task/data
COPY example_tasks/multi-misread-approval-scope/oracle /var/lib/task/oracle

RUN chmod 700 /var/lib/task && \
    mock-slack --db /data/slack.db seed \
      --task-data /var/lib/task/data \
      --task-name multi-misread-approval-scope && \
    mock-gmail --db /data/gmail.db seed \
      --task-data /var/lib/task/data \
      --task-name multi-misread-approval-scope && \
    mock-gdrive --db /data/gdrive.db seed \
      --task-data /var/lib/task/data \
      --task-name multi-misread-approval-scope
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
