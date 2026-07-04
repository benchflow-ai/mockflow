FROM ghcr.io/benchflow-ai/env0:0.1.0

# Remove config so agent cannot discover the DB path
RUN rm -f /etc/env0/config.toml /etc/env0/env.sh

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/slack-search-channel-history/data /tasks/slack-search-channel-history/data
ENV TASKS_DIR=/tasks

# Seed the task-specific scenario
RUN mock-slack --db /data/slack.db seed --scenario task:slack-search-channel-history

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# Mock Slack tokens for the agent
ENV SLACK_BOT_TOKEN=mock-bot-token
ENV SLACK_USER_TOKEN=mock-user-token
