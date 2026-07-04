#!/usr/bin/env bash
# Reference solution: find overshared sensitive files and remove bad permissions.
# The agent must distinguish legitimate external shares (e.g., partner collab docs,
# public blog drafts) from problematic overshares on sensitive files.
set -euo pipefail

# Sensitive file names to lock down
SENSITIVE_NAMES=(
  "api-keys.env"
  "Board Meeting Notes - Q1 2026"
  "Employee Salary Data 2026.xlsx"
  "Team Standup Notes.txt"
)

for name in "${SENSITIVE_NAMES[@]}"; do
  # Find the file ID by exact name. The task image contains more than one page
  # of Drive items, so a single broad files.list can miss target files.
  file_id=$(gws drive files list \
    --params "$(python3 - "$name" <<'PY'
import json
import sys

name = sys.argv[1]
escaped = name.replace("'", "\\'")
print(json.dumps({
    "q": f"name = '{escaped}'",
    "fields": "files(id,name,mimeType)",
    "pageSize": 10,
}))
PY
)" | python3 -c "
import sys, json
files = json.load(sys.stdin).get('files', [])
print(files[0]['id'] if files else '')
")

  if [ -z "$file_id" ]; then
    continue
  fi

  # List permissions and remove overshared ones
  perms_json=$(gws drive permissions list \
    --params "{\"fileId\": \"${file_id}\", \"fields\": \"permissions(id,type,role,emailAddress)\"}")
  echo "$perms_json" | python3 -c "
import sys, json
perms = json.load(sys.stdin)['permissions']
for p in perms:
    if p['role'] != 'owner':
        if p['type'] == 'anyone' or p['type'] == 'user' and p.get('emailAddress', '').split('@')[1] not in ('nexusai.com',):
            print(p['id'])
" | while read -r perm_id; do
    gws drive permissions delete \
      --params "{\"fileId\": \"${file_id}\", \"permissionId\": \"${perm_id}\"}"
  done
done

echo "Done"
