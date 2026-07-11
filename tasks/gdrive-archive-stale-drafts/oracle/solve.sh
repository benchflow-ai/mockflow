#!/usr/bin/env bash
set -euo pipefail

CUTOFF=$(python3 -c "from datetime import datetime, timedelta; print((datetime.utcnow() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ'))")

ARCHIVE_ID=$(gws drive files list \
  --params '{"q": "name = '\''Drafts'\'' and mimeType = '\''application/vnd.google-apps.folder'\'' and trashed = false", "fields": "files(id,name,parents)", "pageSize": 20}' \
  | python3 -c "import json,sys; data=json.load(sys.stdin); files=data.get('files', []); print(files[0]['id'] if files else '')")

if [ -z "$ARCHIVE_ID" ]; then
  echo "Archive/Drafts folder not found" >&2
  exit 1
fi

gws drive files list \
  --params "{\"q\": \"name contains 'Draft' and trashed = false\", \"fields\": \"files(id,name,mimeType,parents,modifiedTime)\", \"pageSize\": 100}" \
  | CUTOFF="$CUTOFF" ARCHIVE_ID="$ARCHIVE_ID" python3 -c "
import json
import os
import subprocess
import sys
from datetime import datetime

cutoff = datetime.fromisoformat(os.environ['CUTOFF'].replace('Z', '+00:00'))
archive_id = os.environ['ARCHIVE_ID']
data = json.load(sys.stdin)

def run_json(args):
    return json.loads(subprocess.check_output(args, text=True))

for file in data.get('files', []):
    if file.get('mimeType') == 'application/vnd.google-apps.folder':
        continue
    modified = datetime.fromisoformat(file['modifiedTime'].replace('Z', '+00:00'))
    if modified >= cutoff:
        continue

    file_id = file['id']
    perms = run_json([
        'gws', 'drive', 'permissions', 'list',
        '--params', json.dumps({'fileId': file_id, 'fields': 'permissions(id,role,type,emailAddress)'})
    ])
    non_owner = [p for p in perms.get('permissions', []) if p.get('role') != 'owner']
    if non_owner:
        continue

    comments = run_json([
        'gws', 'drive', 'comments', 'list',
        '--params', json.dumps({'fileId': file_id, 'fields': 'comments(id)', 'pageSize': 20})
    ])
    if comments.get('comments'):
        continue

    parents = file.get('parents', [])
    old_parent = parents[0] if parents else ''
    params = {'fileId': file_id, 'addParents': archive_id}
    if old_parent:
        params['removeParents'] = old_parent
    subprocess.check_call([
        'gws', 'drive', 'files', 'update',
        '--params', json.dumps(params),
        '--json', '{}',
    ])
"
