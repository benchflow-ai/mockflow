FROM ghcr.io/benchflow-ai/env0:0.1.0

WORKDIR /app
ENV TASK_ROOT=/var/lib/task

COPY example_tasks/gdoc-search-keyword-index/data /var/lib/task/data
COPY example_tasks/gdoc-search-keyword-index/oracle /var/lib/task/oracle

RUN chmod 700 /var/lib/task && \
    mock-gdrive --db /data/gdrive.db seed \
      --task-data /var/lib/task/data \
      --task-name gdoc-search-keyword-index
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
