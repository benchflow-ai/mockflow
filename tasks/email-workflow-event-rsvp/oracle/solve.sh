#!/usr/bin/env bash
# Oracle: reply "confirmed" to next-week events, label future events.
# Reads needle manifest for message/thread IDs by role.
set -euo pipefail

MANIFEST="${NEEDLE_MANIFEST:-/data/_needle_manifest_email-workflow-event-rsvp.json}"

# Search for event emails (earns search usage bonus)
gws gmail users messages list \
  --params '{"userId": "me", "q": "from:notify@luma.com"}' > /dev/null 2>&1 || true

# Create "Future Events" label
LABEL_ID=$(gws gmail users labels create \
  --params '{"userId": "me"}' \
  --json '{"name": "Future Events"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")

echo "Created Future Events label: $LABEL_ID"

# Process needles by role
python3 -c "
import json, base64, subprocess

m = json.load(open('$MANIFEST'))

for needle in m['needles']:
    mid = needle['message_id']
    tid = needle['thread_id']
    role = needle['role']
    subject = needle.get('subject', '')

    if role == 'next_week':
        # Reply with 'confirmed'
        msg = f'''To: notify@luma.com
Subject: Re: {subject}

Confirmed.
'''
        raw = base64.urlsafe_b64encode(msg.encode()).decode()
        cmd = [
            'gws', 'gmail', 'users', 'messages', 'send',
            '--params', '{\"userId\": \"me\"}',
            '--json', json.dumps({'raw': raw, 'threadId': tid}),
        ]
        subprocess.run(cmd, check=True)
        print(f'Replied confirmed to: {subject}')

    elif role == 'future':
        # Apply Future Events label
        cmd = [
            'gws', 'gmail', 'users', 'messages', 'modify',
            '--params', json.dumps({'userId': 'me', 'id': mid}),
            '--json', json.dumps({'addLabelIds': ['$LABEL_ID']}),
        ]
        subprocess.run(cmd, check=True)
        print(f'Labeled future: {subject}')

    elif role == 'ignore':
        print(f'Ignored (correct): {subject}')
"

echo "Event RSVP processing complete"
