FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV SLACK_URL=http://localhost:9005

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/slack-reaction-weekly-leaderboard/data /tasks/slack-reaction-weekly-leaderboard/data
ENV TASKS_DIR=/tasks

RUN mock-slack --db /data/slack.db seed --scenario task:slack-reaction-weekly-leaderboard

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# Mock Slack tokens for the agent
ENV SLACK_BOT_TOKEN=xoxb-mock-bot-token
ENV SLACK_USER_TOKEN=xoxp-mock-user-token

# BenchFlow starts mock-slack from tasks/_manifests/env-0.toml.
